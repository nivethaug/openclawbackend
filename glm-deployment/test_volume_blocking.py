"""Test if network volume is blocking deployment."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

gpu = "NVIDIA GeForce RTX 4090"

# Test 1: WITH network volume (what we want)
print("=== WITH network volume ===")
for cloud in ["COMMUNITY", "SECURE", "ALL"]:
    print(f"  {cloud}...", end=" ", flush=True)
    try:
        r = requests.post(url, json={
            "query": """mutation($inp: PodFindAndDeployOnDemandInput!) {
                podFindAndDeployOnDemand(input: $inp) {
                    id name desiredStatus costPerHr
                }
            }""",
            "variables": {"inp": {
                "cloudType": cloud, "gpuCount": 1, "gpuTypeId": gpu,
                "imageName": "vllm/vllm-openai:latest", "containerDiskInGb": 20,
                "dockerArgs": "echo hello", "ports": "8000/http",
                "networkVolumeId": "s56scam7ck", "volumeMountPath": "/workspace",
                "minMemoryInGb": 15, "minVcpuCount": 4,
            }}
        }, headers=h, timeout=30)
        j = r.json()
        errs = j.get("errors")
        if errs:
            print(f"ERR: {errs[0].get('message', '?')[:120]}")
        else:
            pod = j.get("data", {}).get("podFindAndDeployOnDemand")
            print(f"OK! {pod}")
    except Exception as e:
        print(f"EX: {e}")

# Test 2: WITHOUT network volume (just to test GPU availability)
print("\n=== WITHOUT network volume ===")
for cloud in ["COMMUNITY", "SECURE", "ALL"]:
    print(f"  {cloud}...", end=" ", flush=True)
    try:
        r = requests.post(url, json={
            "query": """mutation($inp: PodFindAndDeployOnDemandInput!) {
                podFindAndDeployOnDemand(input: $inp) {
                    id name desiredStatus costPerHr
                }
            }""",
            "variables": {"inp": {
                "cloudType": cloud, "gpuCount": 1, "gpuTypeId": gpu,
                "imageName": "vllm/vllm-openai:latest", "containerDiskInGb": 20,
                "dockerArgs": "echo hello", "ports": "8000/http",
                "volumeInGb": 10, "volumeMountPath": "/workspace",
                "minMemoryInGb": 15, "minVcpuCount": 4,
            }}
        }, headers=h, timeout=30)
        j = r.json()
        errs = j.get("errors")
        if errs:
            print(f"ERR: {errs[0].get('message', '?')[:120]}")
        else:
            pod = j.get("data", {}).get("podFindAndDeployOnDemand")
            print(f"OK! {pod}")
    except Exception as e:
        print(f"EX: {e}")
import os
