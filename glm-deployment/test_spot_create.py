"""Test creating a SPOT pod with interruptible:true + networkVolumeId."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = "https://api.runpod.io/graphql"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

VOLUME_ID = "s56scam7ck"

def try_deploy(label, pod_input):
    payload = {
        "query": """mutation createPod($inp: PodFindAndDeployOnDemandInput!) {
            podFindAndDeployOnDemand(input: $inp) {
                id name desiredStatus costPerHr podType gpuCount
                machine { gpuDisplayName location }
            }
        }""",
        "variables": {"inp": pod_input}
    }
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    j = r.json()
    errs = j.get("errors", [])
    data = j.get("data", {}).get("podFindAndDeployOnDemand")
    if errs:
        print(f"  {label}: ERROR: {errs[0]['message'][:120]}")
        return None
    elif data:
        print(f"  {label}: SUCCESS!")
        print(f"    id={data['id']} type={data.get('podType')} gpu={data.get('gpuCount')} "
              f"cost=${data.get('costPerHr')}/hr machine={data.get('machine')}")
        # Terminate test pod immediately
        stop = {"query": """mutation($pid: String!) { podTerminate(input: {podId: $pid}) }""",
                "variables": {"pid": data["id"]}}
        requests.post(url, json=stop, headers=headers, timeout=10)
        print(f"    (terminated test pod)")
        return data
    else:
        print(f"  {label}: null response")
        return None

base_input = {
    "gpuCount": 1,
    "gpuTypeId": "NVIDIA RTX PRO 4500 Blackwell",
    "imageName": "vllm/vllm-openai:latest",
    "containerDiskInGb": 20,
    "dockerArgs": "--model /workspace/models/glm-4.7-flash-4bit --quantization gptq_marlin --host 0.0.0.0 --port 8000",
    "ports": "8000/http",
    "networkVolumeId": VOLUME_ID,
    "volumeMountPath": "/workspace",
    "minMemoryInGb": 15,
    "minVcpuCount": 4,
}

print("=" * 70)
print("TEST: Can podFindAndDeployOnDemand create SPOT pods?")
print("=" * 70)

# Test 1: interruptible: true
inp = {**base_input, "cloudType": "COMMUNITY", "interruptible": True}
try_deploy("COMMUNITY + interruptible:true", inp)

# Test 2: cloudType INTERRUPTABLE
inp = {**base_input, "cloudType": "INTERRUPTABLE"}
try_deploy("cloudType=INTERRUPTABLE", inp)

# Test 3: Both
inp = {**base_input, "cloudType": "INTERRUPTABLE", "interruptible": True}
try_deploy("INTERRUPTABLE + interruptible:true", inp)

# Test 4: cloudType SPOT
inp = {**base_input, "cloudType": "SPOT"}
try_deploy("cloudType=SPOT", inp)

# Test 5: COMMUNITY + no network volume (just to see if volume is the blocker)
inp = {**base_input, "cloudType": "COMMUNITY"}
del inp["networkVolumeId"]
del inp["volumeMountPath"]
try_deploy("COMMUNITY (no volume)", inp)

# Test 6: ALL + interruptible
inp = {**base_input, "cloudType": "ALL", "interruptible": True}
try_deploy("ALL + interruptible:true", inp)

print("\nDone.")
import os
