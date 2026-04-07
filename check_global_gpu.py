"""Check GPU availability across ALL data centers (no volume constraint)."""
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

# Get all DCs with stock
r = requests.post(url, json={"query": """query {
    dataCenters {
        id name location
        gpuAvailability {
            gpuTypeId displayName stockStatus
        }
    }
}"""}, headers=h, timeout=15)
dcs = r.json().get("data", {}).get("dataCenters", [])

# Cheap GPUs suitable for GLM-4.7-Flash (needs >=8GB VRAM)
cheap_gpus = {
    "NVIDIA GeForce RTX 4090", "NVIDIA GeForce RTX 3090",
    "NVIDIA RTX A4000", "NVIDIA RTX A5000", "NVIDIA RTX A6000", "NVIDIA RTX A4500",
    "NVIDIA RTX 4000 Ada Generation", "NVIDIA RTX PRO 4500 Blackwell",
    "NVIDIA L4", "NVIDIA GeForce RTX 5090", "NVIDIA GeForce RTX 4080",
    "NVIDIA RTX 2000 Ada Generation",
}

# Get spot pricing for these GPUs
r2 = requests.post(url, json={"query": """query {
    gpuTypes {
        id displayName memoryInGb
        lowestPrice(input: { gpuCount: 1 }) {
            uninterruptablePrice minimumBidPrice
        }
    }
}"""}, headers=h, timeout=15)
gpu_pricing = {}
for g in r2.json().get("data", {}).get("gpuTypes", []):
    gid = g.get("id")
    if gid in cheap_gpus:
        lp = g.get("lowestPrice") or {}
        gpu_pricing[gid] = {
            "vram": g.get("memoryInGb"),
            "spot": lp.get("minimumBidPrice"),
            "od": lp.get("uninterruptablePrice"),
            "name": g.get("displayName"),
        }

print("=" * 100)
print("GLOBAL GPU AVAILABILITY (no volume constraint) — Cheap GPUs with stock")
print("=" * 100)
print(f"{'DC':<12} {'Location':<25} {'GPU':<40} {'Stock':<8} {'Spot $/hr':<10} {'OD $/hr':<10}")
print("-" * 100)

total_options = 0
for dc in sorted(dcs, key=lambda x: x.get("id", "")):
    for g in sorted(dc.get("gpuAvailability") or [], key=lambda x: x.get("gpuTypeId", "")):
        gid = g.get("gpuTypeId", "")
        stock = g.get("stockStatus") or "None"
        if gid in cheap_gpus and stock not in ("None", None, ""):
            pricing = gpu_pricing.get(gid, {})
            spot = pricing.get("spot", "?")
            od = pricing.get("od", "?")
            spot_str = f"${spot:.3f}" if isinstance(spot, (int, float)) and spot < 999 else "N/A"
            od_str = f"${od:.3f}" if isinstance(od, (int, float)) and od < 999 else "N/A"
            print(f"{dc['id']:<12} {dc.get('location','?'):<25} {g.get('displayName','?'):<40} {stock:<8} {spot_str:<10} {od_str:<10}")
            total_options += 1

print("-" * 100)
print(f"\nTotal GPU/DC combos with stock: {total_options}")

# Best bets
print("\n" + "=" * 100)
print("BEST BETS FOR IMMEDIATE DEPLOYMENT (spot < $0.30/hr)")
print("=" * 100)
found = False
for dc in sorted(dcs, key=lambda x: x.get("id", "")):
    for g in dc.get("gpuAvailability") or []:
        gid = g.get("gpuTypeId", "")
        stock = g.get("stockStatus") or "None"
        if gid in cheap_gpus and stock not in ("None", None, ""):
            pricing = gpu_pricing.get(gid, {})
            spot = pricing.get("spot", 999)
            if isinstance(spot, (int, float)) and spot < 0.30:
                print(f"  ✅ {dc['id']:<10} {g.get('displayName','?'):<35} spot=${spot:.3f}/hr  vram={pricing.get('vram','?')}GB")
                found = True
if not found:
    print("  No cheap spot GPUs found globally. Try on-demand instead.")

# EU-RO-1 comparison
print("\n" + "=" * 100)
print("EU-RO-1 ONLY (your volume is here)")
print("=" * 100)
for dc in dcs:
    if dc["id"] == "EU-RO-1":
        for g in sorted(dc.get("gpuAvailability") or [], key=lambda x: x.get("gpuTypeId", "")):
            gid = g.get("gpuTypeId", "")
            stock = g.get("stockStatus") or "None"
            if gid in cheap_gpus:
                pricing = gpu_pricing.get(gid, {})
                print(f"  {g.get('displayName','?'):<40} stock={stock:<8} spot=${pricing.get('spot','?')}/hr od=${pricing.get('od','?')}/hr")
