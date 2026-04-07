#!/usr/bin/env python3
"""
Brute-force discover RunPod GraphQL mutations by trying known names from runpodctl source.
Since introspection is disabled, we probe mutations directly.
"""
import os, sys, json, requests

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
if not API_KEY:
    print("Set RUNPOD_API_KEY"); sys.exit(1)

url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

def try_mutation(name, input_type_name, input_payload, return_fields="id name"):
    """Try calling a mutation with a given name and input type."""
    q = f"""mutation ($inp: {input_type_name}!) {{
      {name}(input: $inp) {{ {return_fields} }}
    }}"""
    r = requests.post(url, json={"query": q, "variables": {"inp": input_payload}}, headers=h, timeout=30)
    j = r.json()
    errs = j.get("errors")
    if errs:
        msg = errs[0].get("message", "")
        code = errs[0].get("extensions", {}).get("code", "")
        return {"ok": False, "msg": msg[:150], "code": code}
    return {"ok": True, "data": j.get("data", {})}

def probe_mutation_names():
    """Try calling mutations with dummy input to discover which exist."""
    candidates = [
        # Pod creation
        ("podCreate", "PodCreateInput"),
        ("createPod", "CreatePodInput"),
        ("podDeploy", "PodDeployInput"),
        ("deployPod", "DeployPodInput"),
        ("podFindAndDeployOnDemand", "PodFindAndDeployOnDemandInput"),
        ("podFindAndDeploySpot", "PodFindAndDeploySpotInput"),
        ("podFindAndDeploy", "PodFindAndDeployInput"),
        ("podStart", "PodStartInput"),
        ("podSecureStart", "PodSecureStartInput"),
        # Spot-specific
        ("podBidResume", "PodBidResumeInput"),
        ("podSpotCreate", "PodSpotCreateInput"),
        ("podInterruptibleCreate", "PodInterruptibleCreateInput"),
        ("podSpotResume", "PodSpotResumeInput"),
        ("podSpotDeploy", "PodSpotDeployInput"),
        # Misc
        ("podStop", "PodStopInput"),
        ("podTerminate", "PodTerminateInput"),
        ("podResume", "PodResumeInput"),
    ]
    
    print("=" * 70)
    print("PROBING MUTATION NAMES")
    print("=" * 70)
    
    found = []
    not_found = []
    
    for name, input_type in candidates:
        # Use empty input to see if mutation exists vs input validation fails
        r = try_mutation(name, input_type, {})
        if "not allowed" in r["msg"] or "Cannot query field" in r["msg"]:
            not_found.append((name, input_type, r["msg"][:80]))
        else:
            found.append((name, input_type, r))
    
    print(f"\n✅ FOUND ({len(found)}):")
    for name, input_type, result in found:
        print(f"  {name}({input_type})")
        if result["ok"]:
            print(f"    → SUCCESS: {json.dumps(result['data'])[:120]}")
        else:
            print(f"    → {result['code']}: {result['msg'][:100]}")
    
    print(f"\n❌ NOT FOUND ({len(not_found)}):")
    for name, input_type, msg in not_found:
        print(f"  {name}({input_type}) — {msg}")
    
    return found

def probe_input_fields(mutation_name, input_type_name):
    """Probe which fields a mutation accepts by sending them one at a time."""
    base_input = {
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
    
    # Fields to probe
    extra_fields = [
        "interruptible",
        "spot",
        "bidPerGpu",
        "deployCost",
        "computeType",
        "name",
        "dataCenterId",
        "cloudType",
    ]
    
    print(f"\n{'=' * 70}")
    print(f"PROBING FIELDS FOR {mutation_name}({input_type_name})")
    print("=" * 70)
    
    # First: try base input
    print("\n[Base input with volume]...")
    r = try_mutation(mutation_name, input_type_name, base_input, "id name desiredStatus costPerHr")
    print(f"  Result: {r}")
    
    # Try with interruptible
    for field in extra_fields:
        if field in base_input:
            continue
        test = dict(base_input)
        test[field] = True if field in ("interruptible", "spot", "supportPublicIp", "startSsh") else "test"
        print(f"\n[+ {field}]...")
        r = try_mutation(mutation_name, input_type_name, test)
        print(f"  Result: {r}")

# ─── Main ─────────────────────────────────────────────────
print("Step 1: Discover available mutations...\n")
found = probe_mutation_names()

print("\n\nStep 2: Probe input fields for creation mutations...\n")
for name, input_type, result in found:
    if "create" in name.lower() or "deploy" in name.lower() or "find" in name.lower():
        probe_input_fields(name, input_type)

print("\n✅ Done.")
