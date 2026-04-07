#!/usr/bin/env python3
"""
Deep probe: Follow up on type hints from RunPod's error messages to find the 
exact input types for pod creation mutations.
"""
import os, sys, json, requests

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
if not API_KEY:
    print("Set RUNPOD_API_KEY"); sys.exit(1)

url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

def try_mutation(name, input_type_name, input_payload, return_fields="id name"):
    q = f"""mutation ($inp: {input_type_name}!) {{
      {name}(input: $inp) {{ {return_fields} }}
    }}"""
    r = requests.post(url, json={"query": q, "variables": {"inp": input_payload}}, headers=h, timeout=30)
    j = r.json()
    errs = j.get("errors")
    if errs:
        return {"ok": False, "msg": errs[0].get("message", ""), "code": errs[0].get("extensions", {}).get("code", "")}
    return {"ok": True, "data": j.get("data", {})}

def probe_type_fields(mutation_name, input_type_name, base_input):
    """Send one extra field at a time. Fields that are ACCEPTED won't give BAD_USER_INPUT."""
    extra_fields = {
        "interruptible": True,
        "deployCost": 0.30,
        "computeType": "GPU",
        "name": "test-pod",
        "dataCenterId": "EU-RO-1",
        "bidPerGpu": 0.20,
        "gpuBidPrice": 0.20,
        "spotPrice": 0.20,
        "maxPrice": 0.30,
        "minBid": 0.10,
        "spot": True,
        "bid": 0.20,
    }
    
    # First: base only (no extras)
    print(f"\n  [Base input]...", end=" ", flush=True)
    r = try_mutation(mutation_name, input_type_name, base_input)
    if r["ok"]:
        print(f"✅ SUCCESS: {json.dumps(r['data'])[:120]}")
    else:
        print(f"{r['code']}: {r['msg'][:100]}")
    
    # Then: base + one extra field at a time
    for field, value in extra_fields.items():
        if field in base_input:
            continue
        test = dict(base_input)
        test[field] = value
        print(f"  [+ {field}={value}]...", end=" ", flush=True)
        r = try_mutation(mutation_name, input_type_name, test)
        if r["ok"]:
            print(f"✅ SUCCESS: {json.dumps(r['data'])[:120]}")
        else:
            # BAD_USER_INPUT about the specific field = field doesn't exist
            if f'"{field}"' in r["msg"] or f".{field}" in r["msg"]:
                print(f"❌ INVALID FIELD")
            elif "SUPPLY_CONSTRAINT" in r["code"]:
                print(f"⚠️ FIELD OK but no capacity")
            elif "BAD_USER_INPUT" in r["code"] and field in r["msg"]:
                print(f"❌ REJECTED: {r['msg'][:80]}")
            else:
                print(f"{r['code']}: {r['msg'][:100]}")

# ─── Follow the type hints ────────────────────────────────
print("=" * 70)
print("PROBING podCreate with various input types")
print("=" * 70)

# From errors we saw suggestions:
# "PodResetInput", "PodResumeInput", "TeamCreateInput", "AddCreditsInput", "PodTemplateInput"
# And from other probes: "PodRentInterruptableInput", "deployCpuPodInput"

base_create = {
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
}

# Try different input type names for podCreate
input_type_candidates = [
    "PodFindAndDeployOnDemandInput",
    "PodRentInterruptableInput",
    "PodTemplateInput",
    "PodResumeInput",
    "PodEditJobInput",
    "PodLockInput",
    "PodResetInput",
]

for itype in input_type_candidates:
    print(f"\n--- podCreate(input: {itype}) ---")
    r = try_mutation("podCreate", itype, base_create)
    if r["ok"]:
        print(f"  ✅ SUCCESS: {json.dumps(r['data'])[:200]}")
    else:
        print(f"  {r['code']}: {r['msg'][:150]}")

# ─── Also try deployCpuPod mutation ───────────────────────
print("\n\n" + "=" * 70)
print("PROBING deployCpuPod mutation")
print("=" * 70)

cpu_input = {
    "cloudType": "COMMUNITY",
    "imageName": "vllm/vllm-openai:latest",
    "containerDiskInGb": 20,
    "dockerArgs": "echo test",
    "ports": "8000/http",
    "minMemoryInGb": 15,
    "minVcpuCount": 4,
    "networkVolumeId": "s56scam7ck",
    "volumeMountPath": "/workspace",
    "name": "test-cpu-pod",
}

r = try_mutation("deployCpuPod", "deployCpuPodInput", cpu_input, "id name desiredStatus")
if r["ok"]:
    print(f"  ✅ {json.dumps(r['data'])[:200]}")
    # Clean up
    pod_id = r["data"].get("deployCpuPod", {}).get("id")
    if pod_id:
        print(f"  Cleaning up pod {pod_id}...")
        requests.post(url, json={"query": 'mutation($pid: String!) { podTerminate(input: {podId: $pid}) }', "variables": {"pid": pod_id}}, headers=h, timeout=15)
else:
    print(f"  {r['code']}: {r['msg'][:200]}")

# ─── Try PodRentInterruptableInput with podFindAndDeployOnDemand ──────
print("\n\n" + "=" * 70)
print("PROBING podFindAndDeployOnDemand with PodRentInterruptableInput")
print("=" * 70)

r = try_mutation("podFindAndDeployOnDemand", "PodRentInterruptableInput", base_create, "id name desiredStatus costPerHr")
if r["ok"]:
    print(f"  ✅ {json.dumps(r['data'])[:200]}")
else:
    print(f"  {r['code']}: {r['msg'][:150]}")

# ─── Now let's find the EXACT valid fields for PodFindAndDeployOnDemandInput ──────
print("\n\n" + "=" * 70)
print("FIELD VALIDATION: PodFindAndDeployOnDemandInput")
print("=" * 70)

# From the probe above, we know:
# - interruptible: BAD_USER_INPUT (invalid field)
# - spot: BAD_USER_INPUT (invalid field)
# - deployCost: ACCEPTED (Float type expected)
# - computeType: ACCEPTED (enum "ComputeType")
# - name: ACCEPTED
# - dataCenterId: ACCEPTED
# Let's find MORE valid fields by trying each possible field

# Try adding env as list of {key, value}
test_env = dict(base_create)
test_env["env"] = [{"key": "TEST", "value": "1"}]
print("\n  [+ env=[{key,value}]]...", end=" ", flush=True)
r = try_mutation("podFindAndDeployOnDemand", "PodFindAndDeployOnDemandInput", test_env)
if r["ok"]:
    print(f"✅")
else:
    if "env" in r["msg"].lower():
        print(f"❌ Invalid env format")
    else:
        print(f"{r['code']}: {r['msg'][:100]}")

# Try PodRentInterruptableInput with podBidResume
print("\n\n" + "=" * 70)
print("PROBING podBidResume with PodRentInterruptableInput")
print("=" * 70)

r = try_mutation("podBidResume", "PodRentInterruptableInput", {"podId": "fake", "bidPerGpu": 0.20, "gpuCount": 1})
if r["ok"]:
    print(f"  ✅ {json.dumps(r['data'])[:200]}")
else:
    print(f"  {r['code']}: {r['msg'][:150]}")

# ─── Check what fields PodRentInterruptableInput accepts ──────
print("\n\n" + "=" * 70)
print("PROBING: What mutation accepts PodRentInterruptableInput?")
print("=" * 70)

# Try various mutation names with this input type
for mname in ["podRentInterruptable", "podRentInterruptible", "rentInterruptable", 
              "podStartInterruptable", "podCreateInterruptable", "podDeployInterruptable",
              "podStartSpot", "podDeploySpot", "podCreateSpot"]:
    r = try_mutation(mname, "PodRentInterruptableInput", base_create)
    if "Cannot query field" not in r["msg"] and "not allowed" not in r["msg"].lower():
        print(f"  {mname}(PodRentInterruptableInput): {r['code']} - {r['msg'][:100]}")

print("\n✅ Done.")
