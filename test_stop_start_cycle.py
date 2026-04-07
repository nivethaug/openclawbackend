"""Full stop â†’ start cycle test for the GLM proxy."""
import os
import requests
import json
import time
import sys

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
POD_ID = "olvdw1yjuoa1mz"
GRAPHQL = "https://api.runpod.io/graphql"
REST = "https://rest.runpod.io/v1"
PROXY_URL = f"https://{POD_ID}-8000.proxy.runpod.net"

headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def get_status():
    query = "query { myself { pods { id desiredStatus name } } }"
    r = requests.post(GRAPHQL, json={"query": query}, headers=headers, timeout=10)
    pods = r.json()["data"]["myself"]["pods"]
    for p in pods:
        if p["id"] == POD_ID:
            return p["desiredStatus"]
    return "not_found"


def stop_pod():
    print("ðŸ›‘ Stopping pod via REST API...")
    r = requests.post(f"{REST}/pods/{POD_ID}/stop", headers=headers, timeout=15)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {json.dumps(r.json(), indent=2)}")
    return r.status_code == 200


def start_pod():
    print("ðŸš€ Starting pod via REST API...")
    r = requests.post(f"{REST}/pods/{POD_ID}/start", headers=headers, timeout=15)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {json.dumps(r.json(), indent=2)}")
    return r.status_code == 200


def wait_for_status(target, timeout=120):
    print(f"   Waiting for status={target}...")
    start = time.time()
    while time.time() - start < timeout:
        status = get_status()
        elapsed = time.time() - start
        print(f"   [{elapsed:.0f}s] status={status}")
        if status == target:
            return True
        time.sleep(5)
    return False


def check_vllm():
    try:
        r = requests.get(f"{PROXY_URL}/v1/models", timeout=5)
        if r.status_code == 200:
            models = r.json()
            print(f"   âœ… vLLM responding: {len(models.get('data', []))} models")
            return True
    except Exception:
        pass
    return False


# â”€â”€â”€ MAIN â”€â”€â”€
print("=" * 60)
print("GLM Proxy: Full Stop â†’ Start Cycle Test")
print("=" * 60)

# Step 1: Check current status
print("\nðŸ“Š Step 1: Current status")
status = get_status()
print(f"   Pod status: {status}")

if status == "RUNNING":
    # Step 2: Stop the pod
    print("\nðŸ›‘ Step 2: Stop the pod")
    if not stop_pod():
        print("   âŒ Stop failed!")
        sys.exit(1)

    # Wait for EXITED
    print("\nâ³ Step 3: Wait for pod to stop")
    if not wait_for_status("EXITED", timeout=60):
        print("   âŒ Pod didn't stop in time!")
        sys.exit(1)
    print("   âœ… Pod stopped!")

elif status == "EXITED":
    print("   Pod already stopped, skipping stop step")

else:
    print(f"   âš ï¸ Unexpected status: {status}")

# Step 3: Start the pod
print("\nðŸš€ Step 4: Start the pod")
if not start_pod():
    print("   âŒ Start failed!")
    sys.exit(1)

# Wait for RUNNING
print("\nâ³ Step 5: Wait for pod to start")
if not wait_for_status("RUNNING", timeout=120):
    print("   âŒ Pod didn't start in time!")
    sys.exit(1)
print("   âœ… Pod is RUNNING!")

# Wait for vLLM
print("\nâ³ Step 6: Wait for vLLM to be ready")
start = time.time()
while time.time() - start < 180:
    if check_vllm():
        elapsed = time.time() - start
        print(f"   âœ… vLLM ready! ({elapsed:.0f}s)")
        break
    elapsed = time.time() - start
    print(f"   [{elapsed:.0f}s] vLLM not ready yet...")
    time.sleep(5)
else:
    print("   âŒ vLLM didn't start in 180s")

# Quick API test
print("\nðŸ“¨ Step 7: Quick API test")
try:
    r = requests.post(
        f"{PROXY_URL}/v1/chat/completions",
        json={
            "model": "default",
            "messages": [{"role": "user", "content": "Say hello in 5 words"}],
            "max_tokens": 50,
        },
        headers=headers,
        timeout=30,
    )
    if r.status_code == 200:
        data = r.json()
        msg = data["choices"][0]["message"]["content"]
        print(f"   âœ… Response: {msg}")
    else:
        print(f"   âŒ API error: {r.status_code} {r.text[:200]}")
except Exception as e:
    print(f"   âŒ Connection error: {e}")

print("\n" + "=" * 60)
print("âœ… Full cycle test complete!")
print("=" * 60)
import os
