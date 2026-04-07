"""Wide search: try ALL GPUs across ALL DCs with COMMUNITY cloud."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

# Get all DCs with their GPU availability
print("Fetching all data centers and GPU availability...")
r = requests.post(url, json={"query": """query {
    dataCenters {
        id name location
        gpuAvailability {
            gpuTypeId displayName stockStatus
        }
    }
}"""}, headers=h, timeout=15)
dcs = r.json().get("data", {}).get("dataCenters", [])

# Collect ALL GPUs with any stock
candidates = []
for dc in dcs:
    gpus = dc.get("gpuAvailability") or []
    for g in gpus:
        stock = g.get("stockStatus") or "None"
        gid = g.get("gpuTypeId") or "?"
        if stock and stock != "None":
            candidates.append((dc["id"], dc.get("location", "?"), gid, g.get("displayName", "?"), stock))

print(f"\nFound {len(candidates)} GPU/DC combos with stock. Trying COMMUNITY cloud deployment...\n")

successes = []
for dc_id, loc, gpu_id, display, stock in candidates:
    # Skip very expensive GPUs (A100, H100, MI300X, B200)
    if any(x in gpu_id.upper() for x in ["A100", "H100", "MI300", "B200", "PRO 6000"]):
        continue
    
    print(f"  {dc_id:10s} {display[:35]:35s} [{stock:6s}]...", end=" ", flush=True)
    try:
        r = requests.post(url, json={
            "query": """mutation deploy($inp: PodFindAndDeployOnDemandInput!) {
                podFindAndDeployOnDemand(input: $inp) {
                    id name desiredStatus costPerHr
                    machine { gpuDisplayName location }
                }
            }""",
            "variables": {"inp": {
                "cloudType": "COMMUNITY",
                "gpuCount": 1,
                "gpuTypeId": gpu_id,
                "imageName": "vllm/vllm-openai:latest",
                "containerDiskInGb": 20,
                "dockerArgs": "echo hello",
                "ports": "8000/http",
                "minMemoryInGb": 15,
                "minVcpuCount": 4,
                "dataCenterId": dc_id,
            }}
        }, headers=h, timeout=30)
        j = r.json()
        errs = j.get("errors")
        if errs:
            msg = errs[0].get("message", "?")[:80]
            print(f"NO: {msg}")
        else:
            pod = j.get("data", {}).get("podFindAndDeployOnDemand")
            if pod:
                print(f"OK! {pod.get('id')} ${pod.get('costPerHr')}/hr {pod.get('machine',{}).get('location','?')}")
                successes.append(pod)
                # DELETE immediately â€” we're just testing
                print(f"      Cleaning up test pod...")
                requests.post(url, json={
                    "query": 'mutation($pid: String!) { podTerminate(input: {podId: $pid}) }',
                    "variables": {"pid": pod["id"]}
                }, headers=h, timeout=15)
                break  # Stop after first success
    except Exception as e:
        print(f"EX: {e}")

if not successes:
    print("\nâŒ No GPU available in ANY data center with COMMUNITY cloud.")
    print("   The RunPod community cloud market is currently saturated.")
    print("   Try again later, or use SECURE cloud (more expensive but more reliable).")
import os
