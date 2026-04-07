"""Test SECURE cloud type for pod deployment."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

gpus = [
    "NVIDIA RTX 4000 Ada Generation",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA RTX PRO 4500 Blackwell",
]

for cloud in ["SECURE", "COMMUNITY", "ALL"]:
    for gpu in gpus:
        print(f"{cloud} / {gpu[:30]}...", end=" ", flush=True)
        try:
            r = requests.post(url, json={
                "query": """mutation($inp: PodFindAndDeployOnDemandInput!) {
                    podFindAndDeployOnDemand(input: $inp) {
                        id name desiredStatus costPerHr
                        machine { gpuDisplayName location }
                    }
                }""",
                "variables": {"inp": {
                    "cloudType": cloud,
                    "gpuCount": 1,
                    "gpuTypeId": gpu,
                    "imageName": "vllm/vllm-openai:latest",
                    "containerDiskInGb": 20,
                    "dockerArgs": "--model /workspace/models/glm-4.7-flash-4bit --quantization gptq_marlin --tensor-parallel-size 1 --max-model-len 4096 --host 0.0.0.0 --port 8000 --trust-remote-code",
                    "ports": "8000/http,22/tcp",
                    "env": [{"key": "VLLM_WORKER_MULTIPROC_METHOD", "value": "spawn"}],
                    "networkVolumeId": "s56scam7ck",
                    "volumeMountPath": "/workspace",
                    "supportPublicIp": True,
                    "startSsh": True,
                    "minMemoryInGb": 15,
                    "minVcpuCount": 4,
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
                    print(f"OK! ID={pod.get('id','?')} cost=${pod.get('costPerHr','?')}/hr")
                else:
                    print("nil pod")
        except Exception as e:
            print(f"EXCEPTION: {e}")
import os
