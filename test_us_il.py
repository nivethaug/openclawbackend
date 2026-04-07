"""Quick test: deploy RTX 4090 in US-IL-1."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

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
        "gpuTypeId": "NVIDIA GeForce RTX 4090",
        "imageName": "vllm/vllm-openai:latest",
        "containerDiskInGb": 20,
        "dockerArgs": "echo hello",
        "ports": "8000/http",
        "minMemoryInGb": 15,
        "minVcpuCount": 4,
        "dataCenterId": "US-IL-1",
    }}
}, headers=h, timeout=30)

print(json.dumps(r.json(), indent=2))
import os
