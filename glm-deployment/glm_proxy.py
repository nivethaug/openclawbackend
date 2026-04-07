"""
GLM Request-Based Proxy
Wakes RunPod pod on demand, forwards requests, auto-stops after idle.

Deployment strategy (3-tier):
  1. RESUME:  podBidResume — fastest if same server has capacity (spot price)
  2. SPOT:    podRentInterruptable — create NEW spot pod (cheaper, can be preempted)
  3. ON-DEMAND: podFindAndDeployOnDemand — fallback (most reliable, higher cost)

No volume lock — deploys to ANY region with available GPUs.
Uses custom Docker image with model baked in for fast startup.

Usage:
  python glm_proxy.py

Environment variables:
  RUNPOD_API_KEY      - Your RunPod API key
  RUNPOD_POD_ID       - Optional fixed pod ID (auto-detected if empty)
  NETWORK_VOLUME_ID   - Optional volume ID (empty = global deploy)
  GLM_IMAGE           - Docker image (default: vllm/vllm-openai:latest)
  PROXY_PORT          - Local proxy port (default: 8080)
  IDLE_TIMEOUT        - Seconds before auto-stop (default: 600)
  SPOT_BID_PER_GPU    - Max spot bid $/hr (default: 0.35)

Then point your apps to: http://localhost:8080/v1/chat/completions
"""

import os
import sys
import time
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# ─── CONFIG ───────────────────────────────────────────────
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "YOUR_RUNPOD_API_KEY")
RUNPOD_POD_ID = os.environ.get("RUNPOD_POD_ID", "")  # auto-detected if empty
NETWORK_VOLUME_ID = os.environ.get("NETWORK_VOLUME_ID", "")  # empty = global deploy
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8080"))
IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "600"))  # 10 minutes
SPOT_BID_PER_GPU = float(os.environ.get("SPOT_BID_PER_GPU", "0.35"))  # max bid $/hr
SPOT_GPU_COUNT = int(os.environ.get("SPOT_GPU_COUNT", "1"))

# GPU fallback list — ordered cheapest first, global search (no volume lock)
GPU_FALLBACKS = [
    "NVIDIA GeForce RTX 3090",           # 24GB, ~$0.10/hr spot — CHEAPEST
    "NVIDIA RTX 4000 Ada Generation",    # 20GB, ~$0.10/hr spot — cheap
    "NVIDIA RTX A4500",                  # 20GB, ~$0.13/hr spot
    "NVIDIA GeForce RTX 4090",           # 24GB, ~$0.20/hr spot — best perf/price
    "NVIDIA RTX A5000",                  # 24GB, ~$0.16/hr spot
    "NVIDIA RTX PRO 4500 Blackwell",     # 32GB, ~$0.34/hr OD — good availability
    "NVIDIA RTX A6000",                  # 48GB, ~$0.32/hr spot — reliable
]

VLLM_IMAGE = os.environ.get("GLM_IMAGE", "vllm/vllm-openai:latest")
VLLM_ARGS = (
    "--model /opt/glm-model "
    "--tensor-parallel-size 1 "
    "--max-model-len 4096 "
    "--gpu-memory-utilization 0.92 "
    "--host 0.0.0.0 --port 8000 "
    "--trust-remote-code"
)

RUNPOD_GRAPHQL = "https://api.runpod.io/graphql"


class PodManager:
    """Manages pod lifecycle: auto-discover, start, stop, deploy."""

    def __init__(self):
        self.last_request_time = 0
        self.lock = threading.Lock()
        self.pod_status = "unknown"
        self._pod_id = RUNPOD_POD_ID  # may be auto-detected

    @property
    def pod_id(self):
        return self._pod_id

    @property
    def pod_proxy_url(self):
        return f"https://{self._pod_id}-8000.proxy.runpod.net"

    def _graphql(self, query, variables=None):
        """Call RunPod GraphQL API."""
        headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}", "Content-Type": "application/json"}
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            resp = requests.post(RUNPOD_GRAPHQL, json=payload, headers=headers, timeout=15)
            j = resp.json()
            if "errors" in j and j["errors"]:
                msg = j["errors"][0].get("message", "unknown")
                raise RuntimeError(msg)
            return j.get("data", {})
        except RuntimeError:
            raise
        except Exception as e:
            print(f"  ⚠️ GraphQL error: {e}")
            return None

    def find_glm_pod(self):
        """Auto-discover GLM pod by image name."""
        data = self._graphql("""query {
            myself { pods {
                id name desiredStatus podType gpuCount costPerHr imageName
                runtime { ports { privatePort publicPort ip isIpPublic } }
            }}
        }""")
        if not data:
            return None
        pods = data.get("myself", {}).get("pods", [])
        for p in pods:
            img = p.get("imageName") or ""
            if "vllm" in img.lower():
                return p
        return None

    def get_status(self):
        """Check pod status — auto-discover if no pod ID set."""
        if self._pod_id:
            try:
                data = self._graphql("""query($pid: String!) {
                    pod(input: {podId: $pid}) { id desiredStatus }
                }""", {"pid": self._pod_id})
                pod = data.get("pod")
                if pod:
                    return pod.get("desiredStatus", "unknown")
            except Exception:
                pass

        # Auto-discover
        p = self.find_glm_pod()
        if p:
            self._pod_id = p["id"]
            return p.get("desiredStatus", "unknown")
        return "not_found"

    def start_pod(self, max_retries=4):
        """Start the GLM pod: 3-tier strategy.
        
        Strategy:
        1. Auto-discover pod if needed
        2. Try podBidResume (fast if same server has capacity, spot price)
        3. Try podRentInterruptable (create NEW spot pod, cheapest)
        4. Fall back to podFindAndDeployOnDemand (on-demand, most reliable)
        """
        # Step 1: Auto-discover
        if not self._pod_id:
            p = self.find_glm_pod()
            if p:
                self._pod_id = p["id"]
                print(f"  📋 Found existing pod: {self._pod_id}")
            else:
                print("  📭 No existing pod — deploying fresh spot...")
                if self._deploy_spot():
                    return True
                print("  💡 Spot failed — trying on-demand...")
                return self._deploy_fresh()

        # Step 2: Try resume (fast path, spot price)
        if self._try_resume(max_retries=max_retries):
            return True

        # Step 3: Try spot deploy (cheapest ongoing cost)
        print("  💰 Resume failed — trying spot deployment...")
        if self._deploy_spot():
            return True

        # Step 4: Final fallback — on-demand (most reliable, higher cost)
        print("  💡 Spot failed — falling back to on-demand...")
        self._delete_pod()
        time.sleep(3)
        return self._deploy_fresh()

    def _try_resume(self, max_retries=4):
        """Try podBidResume with bid escalation."""
        for attempt in range(1, max_retries + 1):
            bid = min(SPOT_BID_PER_GPU * (1 + 0.2 * (attempt - 1)), SPOT_BID_PER_GPU * 2)
            bid = round(bid, 3)
            print(f"  🔄 Resume attempt {attempt}/{max_retries} (bid=${bid})...", end=" ", flush=True)
            try:
                data = self._graphql(
                    """mutation($pid: String!, $bid: Float!, $gpus: Int!) {
                        podBidResume(input: {podId: $pid, bidPerGpu: $bid, gpuCount: $gpus}) {
                            id desiredStatus costPerHr
                        }
                    }""",
                    {"pid": self._pod_id, "bid": bid, "gpus": SPOT_GPU_COUNT},
                )
                if data and data.get("podBidResume"):
                    cost = data["podBidResume"].get("costPerHr", "?")
                    print(f"✅ ${cost}/hr")
                    return True
            except RuntimeError as e:
                if "not enough" in str(e).lower():
                    print("no capacity")
                else:
                    print(f"error: {e}")
            if attempt < max_retries:
                time.sleep(5)
        return False

    def _build_deploy_input(self, gpu_type, cloud, bid=None):
        """Build common input dict for pod creation. Optional volume."""
        inp = {
            "cloudType": cloud,
            "gpuCount": SPOT_GPU_COUNT,
            "gpuTypeId": gpu_type,
            "imageName": VLLM_IMAGE,
            "containerDiskInGb": 30,
            "minVcpuCount": 8,
            "minMemoryInGb": 24,
            "name": "glm-vllm-spot",
            "ports": "8000/http,22/tcp",
            "dockerArgs": VLLM_ARGS,
            "supportPublicIp": True,
            "startSsh": True,
            "env": [{"key": "VLLM_WORKER_MULTIPROC_METHOD", "value": "spawn"}],
        }
        if bid is not None:
            inp["bidPerGpu"] = bid
        if NETWORK_VOLUME_ID:
            inp["networkVolumeId"] = NETWORK_VOLUME_ID
            inp["volumeMountPath"] = "/workspace"
        return inp

    def _deploy_spot(self):
        """Deploy a NEW spot/interruptible pod using podRentInterruptable.
        
        Global search — no volume lock. ALL clouds first for widest pool.
        """
        for gpu_type in GPU_FALLBACKS:
            for cloud in ["ALL", "SECURE", "COMMUNITY"]:
                bid = round(SPOT_BID_PER_GPU * 1.1, 3)
                print(f"  🚀 Spot: {gpu_type} [{cloud}] bid=${bid}...", end=" ", flush=True)
                try:
                    inp = self._build_deploy_input(gpu_type, cloud, bid=bid)
                    data = self._graphql(
                        """mutation($inp: PodRentInterruptableInput!) {
                            podRentInterruptable(input: $inp) {
                                id desiredStatus costPerHr lowestBidPriceToResume
                                machine { gpuDisplayName location }
                            }
                        }""",
                        {"inp": inp},
                    )
                    pod = data.get("podRentInterruptable")
                    if pod:
                        self._pod_id = pod["id"]
                        machine = pod.get("machine") or {}
                        cost = pod.get("costPerHr", "?")
                        lowest = pod.get("lowestBidPriceToResume", "?")
                        print(f"✅ id={self._pod_id} GPU={machine.get('gpuDisplayName','?')} ${cost}/hr (min bid ~${lowest})")
                        return True
                except RuntimeError as e:
                    err = str(e).lower()
                    if any(x in err for x in ["no longer any instances", "supply_constraint", "not enough"]):
                        print("no capacity")
                    elif "bid" in err or "lowest" in err:
                        print("bid too low")
                    else:
                        print(f"error: {err[:80]}")
                time.sleep(2)
        print("  ❌ All spot attempts failed")
        return False

    def _deploy_fresh(self):
        """Deploy a new on-demand pod with global GPU search and optional volume."""
        for gpu_type in GPU_FALLBACKS:
            for cloud in ["ALL", "SECURE"]:
                print(f"  🚀 On-demand: {gpu_type} [{cloud}]...", end=" ", flush=True)
                try:
                    inp = self._build_deploy_input(gpu_type, cloud)
                    data = self._graphql(
                        """mutation($inp: PodFindAndDeployOnDemandInput!) {
                            podFindAndDeployOnDemand(input: $inp) {
                                id desiredStatus costPerHr
                                machine { gpuDisplayName location }
                            }
                        }""",
                        {"inp": inp},
                    )
                    pod = data.get("podFindAndDeployOnDemand")
                    if pod:
                        self._pod_id = pod["id"]
                        machine = pod.get("machine") or {}
                        print(f"✅ id={self._pod_id} GPU={machine.get('gpuDisplayName','?')} ${pod.get('costPerHr','?')}/hr")
                        return True
                except RuntimeError as e:
                    err = str(e).lower()
                    if any(x in err for x in ["no longer", "not enough", "supply_constraint"]):
                        print("no capacity")
                    else:
                        print(f"error: {err[:70]}")
        print("  ❌ All on-demand attempts failed")
        return False

    def _delete_pod(self):
        """Delete current pod (volume data preserved)."""
        if not self._pod_id:
            return
        try:
            self._graphql(
                """mutation($pid: String!) { podTerminate(input: {podId: $pid}) }""",
                {"pid": self._pod_id},
            )
            print(f"  🗑️ Deleted pod {self._pod_id}")
            self._pod_id = ""
        except Exception as e:
            print(f"  ⚠️ Delete failed: {e}")

    def stop_pod(self):
        """Stop the pod via GraphQL podStop."""
        pid = self._pod_id or RUNPOD_POD_ID
        if not pid:
            print(f"  ⚠️ No pod to stop")
            return False
        print(f"🛑 Stopping pod {pid} (idle timeout)...")

        try:
            self._graphql(
                """mutation StopPod($pid: String!) {
                    podStop(input: {podId: $pid}) { id desiredStatus }
                }""",
                {"pid": pid},
            )
            print(f"  ✅ Pod stopped. GPU billing ended.")
            return True
        except Exception as e:
            print(f"  ⚠️ Stop failed: {e}")
            return False

    def wait_until_ready(self, max_wait=420):
        """Wait for pod to be running and vLLM to respond.
        
        First run downloads model from HuggingFace (~3-5 min).
        Subsequent runs with baked-in image are ~60-90s.
        """
        start = time.time()
        while time.time() - start < max_wait:
            if self.is_vllm_responding():
                elapsed = time.time() - start
                print(f"  ✅ Pod ready! ({elapsed:.0f}s)")
                return True

            status = self.get_status()
            elapsed = time.time() - start
            print(f"  ⏳ Waiting... ({elapsed:.0f}s) status={status}")
            time.sleep(5)

        print(f"  ❌ Pod did not become ready in {max_wait}s")
        return False

    def is_vllm_responding(self):
        """Quick check if vLLM is responding."""
        url = self.pod_proxy_url
        if not self._pod_id:
            return False
        try:
            resp = requests.get(f"{url}/v1/models", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def touch(self):
        """Update last request time."""
        self.last_request_time = time.time()

    def idle_watcher(self):
        """Background thread: stop pod after idle timeout."""
        while True:
            time.sleep(30)
            if self.last_request_time > 0:
                idle = time.time() - self.last_request_time
                if idle > IDLE_TIMEOUT:
                    self.stop_pod()
                    self.last_request_time = 0


pod = PodManager()


class ProxyHandler(BaseHTTPRequestHandler):
    """Forward requests to RunPod, wake pod if needed."""

    def _proxy_request(self):
        pod.touch()
        
        # Check if pod is responding
        if not pod.is_vllm_responding():
            # Try to start
            if not pod.start_pod():
                self.send_error(503, "Failed to start pod")
                return
            
            # Wait for it
            print("⏳ Waiting for pod to wake up (~60-90s)...")
            if not pod.wait_until_ready():
                self.send_error(504, "Pod failed to start")
                return

        # Forward the request
        target_url = f"{pod.pod_proxy_url}{self.path}"
        
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Forward headers
            fwd_headers = {
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Authorization": self.headers.get("Authorization", ""),
            }

            resp = requests.request(
                method=self.command,
                url=target_url,
                headers=fwd_headers,
                data=body,
                stream=True,
                timeout=120,
            )

            # Send response status
            self.send_response(resp.status_code)
            
            # Forward response headers
            for key, value in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, value)
            self.end_headers()

            # Stream response body
            for chunk in resp.iter_content(chunk_size=1024):
                if chunk:
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except requests.ConnectionError:
            self.send_error(502, "Pod connection lost")
        except Exception as e:
            self.send_error(500, str(e))

    def do_GET(self):
        self._proxy_request()

    def do_POST(self):
        self._proxy_request()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"  📨 {self.command} {self.path} → {args[0]}")


def main():
    # Validate config
    if RUNPOD_API_KEY == "YOUR_RUNPOD_API_KEY":
        print("❌ Set RUNPOD_API_KEY environment variable!")
        print("   Get it from: https://www.runpod.io/console/user/settings")
        sys.exit(1)

    print("=" * 70)
    print("  GLM vLLM Proxy -- Spot + On-Demand Wake-on-Request (Global)")
    print("=" * 70)
    vol = NETWORK_VOLUME_ID if NETWORK_VOLUME_ID else "none (global)"
    print(f"  Image:       {VLLM_IMAGE}")
    print(f"  Volume:      {vol}")
    print(f"  Proxy:       http://localhost:{PROXY_PORT}/v1/chat/completions")
    print(f"  Spot bid:    ${SPOT_BID_PER_GPU}/hr")
    print(f"  Idle timeout:{IDLE_TIMEOUT}s ({IDLE_TIMEOUT // 60} min)")
    print(f"  Strategy:    resume -> spot -> on-demand")
    if RUNPOD_POD_ID:
        print(f"  Pod ID:      {RUNPOD_POD_ID} (fixed)")
    else:
        print(f"  Pod ID:      auto-detected")
    print("=" * 70)
    print()
    print("  Use this as your API endpoint:")
    print(f"  http://localhost:{PROXY_PORT}/v1/chat/completions")
    print()

    # Start idle watcher
    watcher = threading.Thread(target=pod.idle_watcher, daemon=True)
    watcher.start()
    print("👁️ Idle watcher started")

    # Check current status
    status = pod.get_status()
    print(f"📊 Pod status: {status}")
    
    if status in ("RUNNING", "running"):
        if pod.is_vllm_responding():
            print("✅ vLLM is responding — ready to serve")
        else:
            print("⏳ Pod running but vLLM still loading...")
    else:
        print("💤 Pod is stopped — will wake on first request")

    print()
    print("Proxy running. Press Ctrl+C to stop.")
    print()

    # Start proxy server
    server = HTTPServer(("127.0.0.1", PROXY_PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Proxy stopped")
        server.server_close()


if __name__ == "__main__":
    main()
