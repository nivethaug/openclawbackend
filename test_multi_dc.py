"""Try deploying in different data centers (without network volume)."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

# First, get data center IDs with available GPUs
print("Checking data centers...")
r = requests.post(url, json={"query": """query {
    dataCenters {
        id name location
        gpuAvailability {
            gpuTypeId displayName stockStatus
        }
    }
}"""}, headers=h, timeout=15)
dcs = r.json().get("data", {}).get("dataCenters", [])

# Find DCs with RTX 4090 or RTX 4000 Ada in stock
print("\nDCs with RTX 4090 or RTX 4000 Ada in stock:")
targets = []
for dc in dcs:
    gpus = dc.get("gpuAvailability") or []
    for g in gpus:
        gid = (g.get("gpuTypeId") or "").lower()
        stock = g.get("stockStatus") or "None"
        if stock and stock != "None" and ("rtx 4090" in gid or "rtx 4000 ada" in gid):
            targets.append((dc["id"], dc["name"], dc.get("location"), g.get("gpuTypeId"), stock))
            print(f"  {dc['id']:12s} {dc.get('location','?'):20s} {g.get('gpuTypeId'):45s} {stock}")

# Try to deploy in each DC with COMMUNITY cloud
print("\n\nTrying deployments (COMMUNITY, no volume)...")
for dc_id, dc_name, loc, gpu_id, stock in targets[:5]:
    print(f"  {dc_id}/{gpu_id[:35]}...", end=" ", flush=True)
    try:
        r = requests.post(url, json={
            "query": """mutation($inp: PodFindAndDeployOnDemandInput!) {
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
            msg = errs[0].get("message", "?")[:100]
            print(f"ERR: {msg}")
        else:
            pod = j.get("data", {}).get("podFindAndDeployOnDemand")
            if pod:
                print(f"OK! {pod.get('id')} ${pod.get('costPerHr')}/hr")
            else:
                print("nil")
    except Exception as e:
        print(f"EX: {e}")
import os
