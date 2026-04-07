#!/usr/bin/env python3
"""
Stop/start/restart/status for a RunPod Spot pod (GraphQL).

Usage:
  python pod_control.py status
  python pod_control.py stop
  python pod_control.py start [retries]
  python pod_control.py restart [retries]

Env vars:
  RUNPOD_API_KEY        (required)
  RUNPOD_POD_ID         (default: olvdw1yjuoa1mz)
  SPOT_BID_PER_GPU      (default: 0.263)  dollars per GPU per hour
"""

import os
import sys
import time
import random
import requests

API_KEY = os.environ.get("RUNPOD_API_KEY")
POD_ID = os.environ.get("RUNPOD_POD_ID", "olvdw1yjuoa1mz")
SPOT_BID_PER_GPU = float(os.environ.get("SPOT_BID_PER_GPU", "0.263"))

GRAPHQL_URL = "https://api.runpod.io/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


# ─── GRAPHQL HELPER ───────────────────────────────────────
def graphql(query: str, variables: dict | None = None, timeout: int = 30) -> dict:
    """Execute a GraphQL request. Returns data payload. Raises on errors."""
    payload = {"query": query, "variables": variables or {}}

    try:
        r = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"HTTP request failed: {e}") from e

    j = r.json()
    if "errors" in j and j["errors"]:
        msg = j["errors"][0].get("message", str(j["errors"]))
        code = j["errors"][0].get("extensions", {}).get("code")
        raise RuntimeError(f"GraphQL error{f' [{code}]' if code else ''}: {msg}")

    if "data" not in j:
        raise RuntimeError(f"Unexpected response (no data): {j}")

    return j["data"]


# ─── POD OPERATIONS ───────────────────────────────────────
def get_pod() -> dict:
    """Query pod by ID."""
    data = graphql(
        """query($podId: String!) {
            pod(input: {podId: $podId}) {
                id name desiredStatus podType gpuCount costPerHr lastStatusChange
                runtime { uptimeInSeconds ports { privatePort publicPort ip isIpPublic } }
            }
        }""",
        {"podId": POD_ID},
    )
    pod = data.get("pod")
    if not pod:
        raise RuntimeError(f"Pod not found: {POD_ID}")
    return pod


def show_status() -> None:
    """Print pod status and optionally probe vLLM."""
    pod = get_pod()
    print(f"Pod: {pod.get('name', '?')} ({pod['id']})")
    print(f"  Status:      {pod.get('desiredStatus', '?')}")
    print(f"  Type:        {pod.get('podType', '?')}")
    print(f"  GPUs:        {pod.get('gpuCount', '?')}")
    print(f"  Cost/hr:     ${pod.get('costPerHr', '?')}")
    print(f"  Last change: {pod.get('lastStatusChange', '?')}")
    if str(pod.get("desiredStatus", "")).upper() == "RUNNING":
        check_vllm()


def stop_pod() -> None:
    """Stop the pod via GraphQL podStop."""
    print(f"🛑 Stopping pod {POD_ID}...")
    data = graphql(
        """mutation($podId: String!) {
            podStop(input: {podId: $podId}) { id desiredStatus lastStatusChange }
        }""",
        {"podId": POD_ID},
    )
    pod = data["podStop"]
    print(f"  ✅ Stopped. Status: {pod.get('desiredStatus', '?')}")


def start_spot(max_retries: int = 10, bid_per_gpu: float | None = None) -> bool:
    """Start spot pod via podBidResume with bid ramping and jitter."""
    pod = get_pod()
    gpu_count = int(pod.get("gpuCount") or 1)
    bid = float(bid_per_gpu) if bid_per_gpu is not None else SPOT_BID_PER_GPU
    max_bid = round(bid * 2, 3)  # cap at 2x starting bid

    for attempt in range(1, max_retries + 1):
        print(
            f"🚀 Resuming spot pod {POD_ID} "
            f"(attempt {attempt}/{max_retries}, bid=${bid}/gpu/hr, gpus={gpu_count})..."
        )
        try:
            data = graphql(
                """mutation($podId: String!, $bidPerGpu: Float!, $gpuCount: Int!) {
                    podBidResume(input: {podId: $podId, bidPerGpu: $bidPerGpu, gpuCount: $gpuCount}) {
                        id desiredStatus costPerHr
                    }
                }""",
                {"podId": POD_ID, "bidPerGpu": bid, "gpuCount": gpu_count},
            )
            res = data["podBidResume"]
            print(f"  ✅ Started! status={res.get('desiredStatus')}, cost=${res.get('costPerHr')}/hr")
            print("  ⏳ Waiting for vLLM...")
            for _ in range(60):
                if check_vllm():
                    return True
                time.sleep(5)
            print("  ⚠️ Pod started but vLLM not ready after 5 min")
            return True

        except RuntimeError as e:
            err_str = str(e)
            is_capacity = "not enough gpu" in err_str.lower()
            if attempt % 10 == 0 or not is_capacity:
                print(f"  ❌ {e}")
            if attempt < max_retries:
                bid = round(min(bid * 1.05, max_bid), 3)  # ramp 5% per try, cap 2x
                time.sleep(random.uniform(3, 7))  # jitter

    print(f"  ❌ Failed after {max_retries} attempts. Spot market may be full.")
    print(f"  💡 Options: (1) retry later, (2) redeploy in a different region, (3) start from RunPod console")
    return False


# ─── vLLM CHECK ───────────────────────────────────────────
def check_vllm(port: int = 8000, timeout: int = 5) -> bool:
    """Probe vLLM /v1/models via RunPod proxy."""
    url = f"https://{POD_ID}-{port}.proxy.runpod.net/v1/models"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            models = [m.get("id") for m in r.json().get("data", [])]
            print(f"  ✅ vLLM ready. Models: {models}")
            return True
    except Exception:
        pass
    return False


# ─── CLI ──────────────────────────────────────────────────
def main():
    if not API_KEY:
        print("❌ Set RUNPOD_API_KEY env var first!")
        return 1
    if not POD_ID:
        print("❌ Set RUNPOD_POD_ID env var!")
        return 1

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    retries = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    if cmd == "status":
        show_status()
        return 0

    if cmd == "stop":
        stop_pod()
        return 0

    if cmd == "start":
        ok = start_spot(max_retries=retries)
        return 0 if ok else 2

    if cmd == "restart":
        stop_pod()
        print("Waiting 5s...")
        time.sleep(5)
        ok = start_spot(max_retries=retries)
        return 0 if ok else 2

    print(f"Unknown command: {cmd}")
    print("Usage: python pod_control.py [stop|start|restart|status] [retries]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
