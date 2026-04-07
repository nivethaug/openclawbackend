"""
Robustly check a Runpod pod's status and probe the vLLM service port.
"""
import os
import requests

API_KEY = os.environ.get("RUNPOD_API_KEY")
POD_ID = os.environ.get("RUNPOD_POD_ID", "olvdw1yjuoa1mz")

if not API_KEY:
    raise ValueError("RUNPOD_API_KEY is not set")

GRAPHQL = f"https://api.runpod.io/graphql?api_key={API_KEY}"
headers = {"Content-Type": "application/json"}

query = """
query($podId: String!) {
  pod(input: { podId: $podId }) {
    id
    name
    desiredStatus
    lastStatusChange
    podType
    gpuCount
    costPerHr
    runtime {
      uptimeInSeconds
      ports {
        type
        ip
        isIpPublic
        privatePort
        publicPort
      }
    }
  }
}
"""

r = requests.post(
    GRAPHQL,
    json={"query": query, "variables": {"podId": POD_ID}},
    headers=headers,
    timeout=15,
)
result = r.json()

if "errors" in result:
    raise RuntimeError(result["errors"][0].get("message", str(result["errors"])))

pod = result.get("data", {}).get("pod")
if not pod:
    raise RuntimeError(f"Pod not found: {POD_ID}")

print(f"Pod: {pod['name']}")
print(f"  ID:            {pod['id']}")
print(f"  Status:        {pod['desiredStatus']}")
print(f"  Pod type:      {pod.get('podType', '?')}")
print(f"  GPUs:          {pod.get('gpuCount', '?')}")
print(f"  Cost/hr:       ${pod.get('costPerHr', '?')}")
print(f"  Last change:   {pod.get('lastStatusChange', '?')}")

runtime = pod.get("runtime")
ports = (runtime or {}).get("ports") or []

if pod["desiredStatus"] != "RUNNING":
    print("\nPod is not RUNNING, so service checks are skipped.")
    print("Resume via: python pod_control.py start")
    raise SystemExit(0)

print("\nExposed runtime ports:")
for p in ports:
    print(
        f"  - {p.get('type', '?')} private:{p.get('privatePort', '?')} "
        f"public:{p.get('publicPort', '?')} ip:{p.get('ip', '?')} public_ip:{p.get('isIpPublic', '?')}"
    )

# --- vLLM service probe ---
TARGET_PRIVATE_PORT = 8000
path = "/v1/models"

mapped = next((p for p in ports if p.get("privatePort") == TARGET_PRIVATE_PORT), None)

print("\n--- Probing vLLM endpoint ---")

# Method A: RunPod proxy URL
proxy_url = f"https://{POD_ID}-{TARGET_PRIVATE_PORT}.proxy.runpod.net{path}"
try:
    rp = requests.get(proxy_url, timeout=8)
    print(f"Proxy probe: {rp.status_code} {proxy_url}")
    if rp.status_code == 200:
        data = rp.json().get("data", [])
        for m in data:
            print(f"  Model: {m.get('id', '?')}")
except Exception as e:
    print(f"Proxy probe failed: {e}")

# Method B: Direct public IP + publicPort
if mapped and mapped.get("isIpPublic") and mapped.get("ip"):
    direct_url = f"http://{mapped['ip']}:{mapped.get('publicPort', TARGET_PRIVATE_PORT)}{path}"
    try:
        rd = requests.get(direct_url, timeout=8)
        print(f"Direct probe: {rd.status_code} {direct_url}")
        if rd.status_code == 200:
            data = rd.json().get("data", [])
            for m in data:
                print(f"  Model: {m.get('id', '?')}")
    except Exception as e:
        print(f"Direct probe failed: {e}")
