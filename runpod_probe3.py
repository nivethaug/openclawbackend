#!/usr/bin/env python3
"""
Probe PodRentInterruptableInput to find its exact accepted fields.
The mutation podRentInterruptable(PodRentInterruptableInput!) EXISTS.
"""
import os, sys, json, requests

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
if not API_KEY:
    print("Set RUNPOD_API_KEY"); sys.exit(1)

url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

def try_rent(payload, return_fields="id name desiredStatus costPerHr"):
    q = f"""mutation ($inp: PodRentInterruptableInput!) {{
      podRentInterruptable(input: $inp) {{ {return_fields} }}
    }}"""
    r = requests.post(url, json={"query": q, "variables": {"inp": payload}}, headers=h, timeout=30)
    j = r.json()
    errs = j.get("errors")
    if errs:
        return {"ok": False, "msg": errs[0].get("message", ""), "code": errs[0].get("extensions", {}).get("code", "")}
    return {"ok": True, "data": j.get("data", {})}

# ─── Strategy: Try subsets of fields to find which are valid ──
print("=" * 70)
print("FINDING VALID FIELDS FOR PodRentInterruptableInput")
print("=" * 70)

# Start with minimal possible fields and add one at a time
# If a field doesn't exist, we get BAD_USER_INPUT about it

# First: try completely empty
print("\n--- Empty input ---")
r = try_rent({})
print(f"  {r}")

# Try individual fields one at a time
test_fields = {
    "podId": "fake123",
    "gpuTypeId": "NVIDIA GeForce RTX 4090",
    "gpuCount": 1,
    "cloudType": "COMMUNITY",
    "imageName": "vllm/vllm-openai:latest",
    "containerDiskInGb": 20,
    "dockerArgs": "echo test",
    "ports": "8000/http",
    "minMemoryInGb": 15,
    "minVcpuCount": 4,
    "networkVolumeId": "s56scam7ck",
    "volumeMountPath": "/workspace",
    "supportPublicIp": True,
    "startSsh": True,
    "bidPerGpu": 0.20,
    "bid": 0.20,
    "deployCost": 0.30,
    "dataCenterId": "EU-RO-1",
    "name": "test-spot",
    "env": [{"key": "TEST", "value": "1"}],
    "computeType": "GPU",
}

print("\n--- Probing individual fields ---")
valid = []
invalid = []
for field, value in test_fields.items():
    r = try_rent({field: value})
    status = ""
    if r["ok"]:
        status = "✅ ACCEPTED (no error)"
        valid.append(field)
    elif "SUPPLY_CONSTRAINT" in r.get("code", ""):
        status = "⚠️ VALID (supply constraint = past validation)"
        valid.append(field)
    elif "BAD_USER_INPUT" in r.get("code", "") and field in r["msg"]:
        status = f"❌ INVALID: {r['msg'][:80]}"
        invalid.append(field)
    elif "INTERNAL_SERVER_ERROR" in r.get("code", ""):
        status = "⚠️ VALID (internal error = past validation)"
        valid.append(field)
    elif "RUNPOD" in r.get("code", ""):
        status = f"⚠️ RUNPOD ERROR: {r['msg'][:80]}"
        valid.append(field)  # Past field validation
    else:
        status = f"? {r['code']}: {r['msg'][:80]}"
    print(f"  {field:25s} → {status}")

print(f"\n✅ VALID FIELDS ({len(valid)}): {sorted(valid)}")
print(f"❌ INVALID FIELDS ({len(invalid)}): {sorted(invalid)}")

# ─── Now try a full deployment with all valid fields ──────
print("\n\n" + "=" * 70)
print("FULL DEPLOYMENT ATTEMPT")
print("=" * 70)

full_input = {
    "cloudType": "COMMUNITY",
    "gpuCount": 1,
    "gpuTypeId": "NVIDIA GeForce RTX 4090",
    "imageName": "vllm/vllm-openai:latest",
    "containerDiskInGb": 20,
    "dockerArgs": "echo test",
    "ports": "8000/http",
    "minMemoryInGb": 15,
    "minVcpuCount": 4,
    "networkVolumeId": "s56scam7ck",
    "volumeMountPath": "/workspace",
    "supportPublicIp": True,
    "startSsh": True,
    "dataCenterId": "EU-RO-1",
    "name": "glm-spot",
    "bidPerGpu": 0.22,
}

print(f"Input: {json.dumps(full_input, indent=2)}")
r = try_rent(full_input)
print(f"\nResult: {r}")

if r["ok"]:
    pod = r["data"].get("podRentInterruptable", {})
    print(f"\n🎉 SPOT POD CREATED!")
    print(f"  ID:    {pod.get('id')}")
    print(f"  Name:  {pod.get('name')}")
    print(f"  Status:{pod.get('desiredStatus')}")
    print(f"  Cost:  ${pod.get('costPerHr')}/hr")
elif r["code"] == "SUPPLY_CONSTRAINT":
    print("\n⚠️ No capacity for RTX 4090 in EU-RO-1. Trying fallback GPUs...")
    
    gpus = [
        "NVIDIA RTX PRO 4500 Blackwell",
        "NVIDIA RTX 4000 Ada Generation", 
        "NVIDIA GeForce RTX 5090",
        "NVIDIA A100-SXM4-80GB",
    ]
    clouds = ["COMMUNITY", "ALL", "SECURE"]
    
    for gpu in gpus:
        for cloud in clouds:
            inp = dict(full_input)
            inp["gpuTypeId"] = gpu
            inp["cloudType"] = cloud
            print(f"\n  {gpu} [{cloud}]...", end=" ", flush=True)
            r = try_rent(inp)
            if r["ok"]:
                pod = r["data"].get("podRentInterruptable", {})
                print(f"\n🎉 SPOT POD CREATED!")
                print(f"  ID:    {pod.get('id')}")
                print(f"  Name:  {pod.get('name')}")
                print(f"  Status:{pod.get('desiredStatus')}")
                print(f"  Cost:  ${pod.get('costPerHr')}/hr")
                sys.exit(0)
            elif "SUPPLY_CONSTRAINT" in r.get("code", ""):
                print("no capacity")
            elif "INTERNAL_SERVER_ERROR" in r.get("code", ""):
                print("server error")
            else:
                print(f"{r['code']}: {r['msg'][:60]}")
    
    print("\n\n❌ All GPUs failed. Supply is tight right now.")
else:
    print(f"\n❌ {r['code']}: {r['msg'][:200]}")

print("\n✅ Done.")
