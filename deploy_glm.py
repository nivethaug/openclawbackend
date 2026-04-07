#!/usr/bin/env python3
"""
Deploy GLM-4.7-Flash on RunPod — global GPU search, no volume lock.

Strategy:
  - Custom Docker image with model baked in (glm-vllm:4.7-flash-4bit)
  - No network volume dependency -> deploy to ANY region with GPU availability
  - Fallback: if custom image unavailable, use vllm/vllm-openai:latest + HF download
  - 3-tier start: RESUME -> SPOT (podRentInterruptable) -> ON-DEMAND

RunPod Spot Pricing (confirmed via API probing, April 2026):
  1. SPOT:    podRentInterruptable -> cheapest (40-60% less than on-demand)
  2. STOP:    podStop -> stops billing ($0/hr while stopped)
  3. RESUME:  podBidResume -> resumes stopped spot pod at spot price
  4. ON-DEMAND: podFindAndDeployOnDemand -> fallback (most reliable, higher cost)

Usage:
  python deploy_glm.py status          # Check current pod + vLLM status
  python deploy_glm.py start           # Smart resume -> spot -> on-demand
  python deploy_glm.py stop            # Stop pod (keep for later resume)
  python deploy_glm.py stop --delete   # Stop and delete pod
  python deploy_glm.py deploy          # Force fresh deployment
  python deploy_glm.py test            # Quick API test
  python deploy_glm.py gpus            # Show GPU fallback list

Env vars:
  RUNPOD_API_KEY        (required)
  RUNPOD_POD_ID         (optional, auto-detected)
  NETWORK_VOLUME_ID     (optional, uses volume if set)
  GLM_IMAGE             (optional, custom image tag)
"""

import os
import sys
import time
import json
import requests

# ─── CONFIG ───────────────────────────────────────────────
API_KEY = os.environ.get("RUNPOD_API_KEY", "")
NETWORK_VOLUME_ID = os.environ.get("NETWORK_VOLUME_ID", "")  # empty = no volume (global deploy)
VOLUME_MOUNT_PATH = "/workspace"

# Docker image — use custom image with model baked in for zero-delay startup
# Build & push first: see docker/glm-vllm/Dockerfile
# Falls back to stock image if custom not available.
IMAGE = os.environ.get("GLM_IMAGE", "vllm/vllm-openai:latest")

CONTAINER_DISK_GB = 30  # enough for model (~16GB) + vllm + overhead
PORTS = "8000/http,22/tcp"
ENV_JSON = '{"VLLM_WORKER_MULTIPROC_METHOD":"spawn"}'

# vLLM args — works with custom image (model at /opt/glm-model) OR stock image (HF auto-download)
# Custom image: model pre-loaded, no HF download needed, transformers 5.x baked in
# Stock image: will try to download from HF, may fail if transformers is too old
VLLM_ARGS = (
    "--model /opt/glm-model "
    "--tensor-parallel-size 1 "
    "--max-model-len 4096 "
    "--gpu-memory-utilization 0.92 "
    "--host 0.0.0.0 --port 8000 "
    "--trust-remote-code"
)

# Global GPU fallback list — ordered cheapest first
# NO volume constraint -> can deploy ANYWHERE in the world
# All work for GLM-4.7-Flash 4-bit (~6GB VRAM with gptq_marlin)
GPU_FALLBACKS = [
    "NVIDIA GeForce RTX 3090",           # 24GB, ~$0.10/hr spot — CHEAPEST, widely available
    "NVIDIA RTX 4000 Ada Generation",    # 20GB, ~$0.10/hr spot — cheap, good availability
    "NVIDIA RTX A4500",                  # 20GB, ~$0.13/hr spot
    "NVIDIA GeForce RTX 4090",           # 24GB, ~$0.20/hr spot — best performance/price
    "NVIDIA RTX A5000",                  # 24GB, ~$0.16/hr spot
    "NVIDIA RTX PRO 4500 Blackwell",     # 32GB, ~$0.34/hr OD — new, good availability
    "NVIDIA RTX A6000",                  # 48GB, ~$0.32/hr spot — overkill but reliable
]

GRAPHQL_URL = "https://api.runpod.io/graphql"
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}


# ─── GRAPHQL HELPER ───────────────────────────────────────
def gql(query, variables=None, timeout=30):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if "errors" in j and j["errors"]:
        msg = j["errors"][0].get("message", str(j["errors"]))
        raise RuntimeError(f"GraphQL: {msg}")
    return j.get("data", {})


# ─── POD DISCOVERY ────────────────────────────────────────
def find_glm_pod():
    """Find existing GLM pod (by image name containing 'vllm')."""
    data = gql("""query {
        myself { pods {
            id name desiredStatus podType gpuCount costPerHr imageName
            lastStatusChange
            runtime { ports { privatePort publicPort ip isIpPublic } }
        }}
    }""")
    pods = data.get("myself", {}).get("pods", [])
    for p in pods:
        img = p.get("imageName") or ""
        if "vllm" in img.lower() or "glm" in (p.get("name") or "").lower():
            return p
    return None


def get_pod_by_id(pod_id):
    """Get pod details by ID."""
    data = gql("""query($pid: String!) {
        pod(input: {podId: $pid}) {
            id name desiredStatus podType gpuCount costPerHr imageName
            lastStatusChange
            runtime { uptimeInSeconds ports { privatePort publicPort ip isIpPublic } }
        }
    }""", {"pid": pod_id})
    return data.get("pod")


# ─── vLLM CHECK ───────────────────────────────────────────
def check_vllm(pod_id, timeout=5):
    """Probe vLLM /v1/models via RunPod proxy."""
    url = f"https://{pod_id}-8000.proxy.runpod.net/v1/models"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            models = [m.get("id") for m in r.json().get("data", [])]
            return models
    except Exception:
        pass
    return None


def wait_for_vllm(pod_id, max_wait=300):
    """Wait for vLLM to be ready, return models or None."""
    print(f"  ⏳ Waiting for vLLM to load model (first run downloads from HF, ~3-5 min)...")
    start = time.time()
    while time.time() - start < max_wait:
        models = check_vllm(pod_id)
        if models:
            elapsed = int(time.time() - start)
            print(f"  ✅ vLLM ready in {elapsed}s. Models: {models}")
            return models
        time.sleep(5)
    print(f"  ⚠️ vLLM not ready after {max_wait}s")
    return None


# ─── POD OPERATIONS ───────────────────────────────────────
def show_status():
    """Show current pod and vLLM status."""
    pod = find_glm_pod()
    if not pod:
        print("📭 No GLM pod found. Use 'deploy' to create one.")
        return
    pid = pod["id"]
    status = pod.get("desiredStatus", "?")
    gpu = pod.get("gpuCount", "?")
    cost = pod.get("costPerHr", "?")
    img = pod.get("imageName", "?")
    print(f"Pod: {pod.get('name', '?')} ({pid})")
    print(f"  Status:    {status}")
    print(f"  Type:      {pod.get('podType', '?')}")
    print(f"  GPUs:      {gpu}")
    print(f"  Cost/hr:   ${cost}")
    print(f"  Image:     {img}")
    print(f"  Changed:   {pod.get('lastStatusChange', '?')}")

    if status == "RUNNING":
        models = check_vllm(pid)
        if models:
            print(f"  vLLM:      ✅ {models}")
        else:
            print(f"  vLLM:      ⏳ Loading...")


def stop_pod(delete=False):
    """Stop (and optionally delete) the GLM pod."""
    pod = find_glm_pod()
    if not pod:
        print("📭 No GLM pod found.")
        return
    pid = pod["id"]

    if delete:
        print(f"🗑️ Deleting pod {pid}...")
        gql("""mutation($pid: String!) {
            podTerminate(input: {podId: $pid})
        }""", {"pid": pid})
        vol_msg = f" Volume {NETWORK_VOLUME_ID} preserved." if NETWORK_VOLUME_ID else ""
        print(f"  ✅ Pod deleted.{vol_msg}")
    else:
        print(f"🛑 Stopping pod {pid}...")
        gql("""mutation($pid: String!) {
            podStop(input: {podId: $pid}) { id desiredStatus }
        }""", {"pid": pid})
        print(f"  ✅ Pod stopped. Use 'start' to resume or 'deploy' to redeploy.")


def try_resume(pod_id, gpu_count=1, max_bid=0.30):
    """Try to resume existing spot pod with podBidResume."""
    print(f"🔄 Trying to resume existing pod {pod_id}...")
    for bid in [0.10, 0.15, 0.20, 0.25, max_bid]:
        print(f"  Bid: ${bid:.3f}/gpu/hr...", end=" ", flush=True)
        try:
            data = gql("""mutation($pid: String!, $bid: Float!, $gpus: Int!) {
                podBidResume(input: {podId: $pid, bidPerGpu: $bid, gpuCount: $gpus}) {
                    id desiredStatus costPerHr
                }
            }""", {"pid": pod_id, "bid": bid, "gpus": gpu_count})
            res = data["podBidResume"]
            print(f"✅ Started at ${res.get('costPerHr', '?')}/hr")
            return True
        except RuntimeError as e:
            if "not enough" in str(e).lower():
                print("no capacity")
            else:
                print(f"error: {e}")
        time.sleep(2)
    return False


def _build_deploy_input(gpu_type, cloud, bid=None):
    """Build common input dict for pod creation mutations.
    
    If NETWORK_VOLUME_ID is set, includes volume mount.
    Otherwise deploys volume-free for global GPU access.
    Uses dockerArgs (works with both spot and on-demand mutations).
    """
    env_list = [{"key": k, "value": v} for k, v in json.loads(ENV_JSON).items()]
    inp = {
        "cloudType": cloud,
        "gpuCount": 1,
        "gpuTypeId": gpu_type,
        "imageName": IMAGE,
        "containerDiskInGb": CONTAINER_DISK_GB,
        "minVcpuCount": 8,
        "minMemoryInGb": 24,
        "name": "glm-vllm-spot",
        "ports": PORTS,
        "dockerArgs": VLLM_ARGS,
        "supportPublicIp": True,
        "startSsh": True,
        "env": env_list,
    }
    if bid is not None:
        inp["bidPerGpu"] = bid
    # Only add volume if configured
    if NETWORK_VOLUME_ID:
        inp["networkVolumeId"] = NETWORK_VOLUME_ID
        inp["volumeMountPath"] = VOLUME_MOUNT_PATH
    return inp


def deploy_spot(preferred_gpu=None, max_bid=0.55):
    """Create a NEW spot/interruptible pod using podRentInterruptable.
    
    Global search — no volume lock means ANY region with GPU availability.
    Tries ALL clouds first (widest pool), then SECURE, then COMMUNITY.
    """
    gpus_to_try = [preferred_gpu] if preferred_gpu else GPU_FALLBACKS
    gpus_to_try = [g for g in gpus_to_try if g]
    bid = round(max_bid * 1.1, 3)  # slight buffer over minimum

    for gpu_type in gpus_to_try:
        for cloud in ["ALL", "SECURE", "COMMUNITY"]:
            label = f"{gpu_type} [{cloud}] bid=${bid}"
            print(f"🚀 Spot deploy: {label}...", flush=True)
            try:
                inp = _build_deploy_input(gpu_type, cloud, bid=bid)
                data = gql("""mutation($inp: PodRentInterruptableInput!) {
                    podRentInterruptable(input: $inp) {
                        id name desiredStatus costPerHr gpuCount imageName lastStatusChange
                        lowestBidPriceToResume
                        machine { gpuDisplayName location }
                    }
                }""", {"inp": inp})
                pod = data["podRentInterruptable"]
                pid = pod["id"]
                machine = pod.get("machine") or {}
                cost = pod.get("costPerHr", "?")
                lowest = pod.get("lowestBidPriceToResume", "?")
                print(f"  ✅ Spot pod created!")
                print(f"     ID:      {pid}")
                print(f"     GPU:     {machine.get('gpuDisplayName', '?')}")
                print(f"     Region:  {machine.get('location', '?')}")
                print(f"     Cost:    ${cost}/hr (min bid ~${lowest})")
                return pid
            except RuntimeError as e:
                err = str(e).lower()
                if any(x in err for x in ["no longer any instances", "supply_constraint", "not enough"]):
                    print(f"  ❌ No capacity")
                elif "bid" in err or "lowest" in err:
                    print(f"  ❌ Bid too low (try increasing SPOT_BID_PER_GPU)")
                else:
                    print(f"  ❌ {err[:100]}")
                continue
    print(f"\n❌ All spot attempts failed.")
    return None


def deploy_new_pod(preferred_gpu=None, max_rounds=2):
    """Create a fresh ON-DEMAND pod with podFindAndDeployOnDemand.
    
    Global search — no volume lock. Falls back when spot deployment fails.
    Tries ALL first (widest pool), then SECURE.
    """
    gpus_to_try = [preferred_gpu] if preferred_gpu else GPU_FALLBACKS
    gpus_to_try = [g for g in gpus_to_try if g]
    cloud_types = ["ALL", "SECURE"]

    for round_n in range(1, max_rounds + 1):
        if round_n > 1:
            print(f"\n  Round {round_n}/{max_rounds} -- retrying...")
            time.sleep(5)
        
        for gpu_type in gpus_to_try:
            for cloud in cloud_types:
                label = f"{gpu_type} [{cloud}]"
                print(f"🚀 On-demand: {label}...", flush=True)
                try:
                    inp = _build_deploy_input(gpu_type, cloud)
                    data = gql("""mutation($inp: PodFindAndDeployOnDemandInput!) {
                        podFindAndDeployOnDemand(input: $inp) {
                            id name desiredStatus costPerHr gpuCount imageName lastStatusChange
                            machine { gpuDisplayName location }
                        }
                    }""", {"inp": inp})
                    pod = data["podFindAndDeployOnDemand"]
                    pid = pod["id"]
                    machine = pod.get("machine") or {}
                    print(f"  ✅ Deployed!")
                    print(f"     ID:      {pid}")
                    print(f"     GPU:     {machine.get('gpuDisplayName', '?')}")
                    print(f"     Region:  {machine.get('location', '?')}")
                    print(f"     Cost:    ${pod.get('costPerHr', '?')}/hr")
                    return pid
                except RuntimeError as e:
                    err = str(e)
                    if "no longer any instances" in err.lower() or "not enough" in err.lower():
                        print(f"  ❌ No capacity")
                    elif "something went wrong" in err.lower():
                        print(f"  ❌ Server error")
                    else:
                        print(f"  ❌ {err[:100]}")
                    continue
    print(f"\n❌ All on-demand attempts failed after {max_rounds} rounds.")
    print(f"   GPU supply is very tight. Try again later or use a different GPU.")
    return None


def start_or_deploy():
    """Smart start: 3-tier strategy — resume → spot → on-demand."""
    pod = find_glm_pod()
    
    if not pod:
        print("📭 No existing GLM pod found.")
        # Try spot first (cheapest)
        print("💰 Trying spot deployment...")
        pid = deploy_spot()
        if pid:
            wait_for_vllm(pid)
            return True
        # Spot failed — try on-demand
        print("💡 Spot failed — trying on-demand...")
        pid = deploy_new_pod()
        if pid:
            wait_for_vllm(pid)
            return True
        return False

    pid = pod["id"]
    status = pod.get("desiredStatus", "?")
    gpu_count = pod.get("gpuCount") or 1

    if status == "RUNNING":
        models = check_vllm(pid)
        if models:
            print(f"✅ Pod {pid} already running with {models}")
            return True
        else:
            print(f"⏳ Pod {pid} running but vLLM not ready yet...")
            return wait_for_vllm(pid) is not None

    # Pod exists but stopped — try resume first
    print(f"📋 Found stopped pod {pid} (status={status})")
    if try_resume(pid, gpu_count=gpu_count):
        return wait_for_vllm(pid) is not None

    # Resume failed — try spot deploy
    print(f"\n💰 Resume failed. Trying spot deployment...")
    pid = deploy_spot()
    if pid:
        return wait_for_vllm(pid) is not None

    # Spot failed — delete and try on-demand
    print(f"\n💡 Spot failed. Trying on-demand...")
    stop_pod(delete=True)
    time.sleep(3)
    pid = deploy_new_pod(max_rounds=2)
    if pid:
        return wait_for_vllm(pid) is not None
    return False


def quick_test():
    """Send a test request to the GLM API."""
    pod = find_glm_pod()
    if not pod:
        print("❌ No GLM pod found. Deploy first.")
        return False
    
    pid = pod["id"]
    url = f"https://{pid}-8000.proxy.runpod.net/v1/chat/completions"
    
    print(f"🧪 Testing API at {url}...")
    try:
        r = requests.post(url, json={
            "model": "zai-org/GLM-4.7-Flash",
            "messages": [{"role": "user", "content": "Say hello in 5 words"}],
            "max_tokens": 50,
            "temperature": 0.7,
        }, timeout=30)
        
        if r.status_code == 200:
            resp = r.json()
            content = resp["choices"][0]["message"]["content"]
            usage = resp.get("usage", {})
            print(f"  ✅ Response: {content}")
            print(f"  📊 Tokens: {usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out")
            return True
        else:
            print(f"  ❌ HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


# ─── CLI ──────────────────────────────────────────────────
def main():
    if not API_KEY:
        print("❌ Set RUNPOD_API_KEY env var!")
        return 1

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    # Show config on every command
    vol = NETWORK_VOLUME_ID if NETWORK_VOLUME_ID else "none (global)"
    print(f"Image: {IMAGE} | Volume: {vol} | GPUs: {len(GPU_FALLBACKS)}")
    print()

    if cmd == "status":
        show_status()
        return 0

    if cmd == "start":
        return 0 if start_or_deploy() else 2

    if cmd == "stop":
        delete = "--delete" in sys.argv
        stop_pod(delete=delete)
        return 0

    if cmd == "deploy":
        # Force fresh deployment (spot first, then on-demand)
        pod = find_glm_pod()
        if pod and pod.get("desiredStatus") not in ("EXITED", "STOPPED"):
            stop_pod(delete=True)
            time.sleep(3)
        gpu = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
        # Try spot first
        pid = deploy_spot(preferred_gpu=gpu)
        if pid:
            wait_for_vllm(pid)
            return 0
        # Spot failed — try on-demand
        print("\n💡 Spot failed — trying on-demand...")
        pid = deploy_new_pod(preferred_gpu=gpu)
        if pid:
            wait_for_vllm(pid)
            return 0
        return 2

    if cmd == "test":
        return 0 if quick_test() else 2

    if cmd == "gpus":
        # Show GPU fallback list
        print("GPU fallback order:")
        for i, gpu in enumerate(GPU_FALLBACKS):
            print(f"  {i+1}. {gpu}")
        return 0

    print(f"Unknown: {cmd}")
    print("Usage: python deploy_glm.py [status|start|stop|deploy|test|gpus]")
    print("  status       Show pod + vLLM status")
    print("  start        Resume or deploy pod")
    print("  stop         Stop pod (--delete to remove)")
    print("  deploy [gpu] Force fresh deployment with optional GPU type")
    print("  test         Quick API test")
    print("  gpus         Show GPU fallback list")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
