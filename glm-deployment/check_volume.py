"""Query GPU availability across regions.

Network volume is in EU-RO-1. Check which regions have cheap GPUs available,
then we can decide: keep volume in EU-RO-1 or migrate it.
"""
import os, requests, json
API_KEY = os.environ.get("RUNPOD_API_KEY")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"

# First: what GPUs are available in EU-RO-1 (where volume lives)?
print("=" * 70)
print("EU-RO-1 (YOUR NETWORK VOLUME REGION) — GPUs with stock")
print("=" * 70)
q = """query {
  gpuTypes {
    id displayName memoryInGb
    lowestPrice(input: { gpuCount: 1, dataCenterId: "EU-RO-1" }) {
      stockStatus minimumBidPrice uninterruptablePrice
    }
  }
}"""
r = requests.post(url, json={"query": q}, timeout=15)
d = r.json()
if "errors" in d:
    print("  ERROR:", d["errors"])
else:
    gpus = d.get("data", {}).get("gpuTypes", [])
    found = []
    for g in gpus:
        lp = g.get("lowestPrice", {})
        bid = lp.get("minimumBidPrice")
        stock = lp.get("stockStatus")
        if bid and stock and stock != "None":
            found.append((bid, g.get("memoryInGb",0), g.get("displayName","?"), g["id"], stock))
    found.sort()
    if not found:
        print("  ❌ NO GPUs available in EU-RO-1")
    else:
        print(f"  {'$/hr':>6s} {'VRAM':>5s} {'Name':35s} {'GPU ID':35s} {'Stock'}")
        for bid, vram, name, gid, stock in found:
            print(f"  ${bid:.3f} {vram:4.0f}GB {name:35s} {gid:35s} {stock}")

# Now scan ALL data centers for cheap GPUs (<= $0.20/hr, >=8GB VRAM)
# to find the best region for migration
print()
print("=" * 70)
print("SCANNING ALL REGIONS — cheapest GPU with stock (<= $0.15/hr, >=8GB)")
print("=" * 70)

# Get data center list
dc_q = """{ dataCenters { id name } }"""
dc_r = requests.post(url, json={"query": dc_q}, timeout=10)
dcs = dc_r.json().get("data", {}).get("dataCenters", [])

region_results = []
for dc in dcs:
    dc_id = dc["id"]
    q = """query ($dc: String!) {
      gpuTypes {
        id displayName memoryInGb
        lowestPrice(input: { gpuCount: 1, dataCenterId: $dc }) {
          stockStatus minimumBidPrice uninterruptablePrice
        }
      }
    }"""
    r = requests.post(url, json={"query": q, "variables": {"dc": dc_id}}, timeout=10)
    d = r.json()
    if "errors" in d:
        continue
    gpus = d.get("data", {}).get("gpuTypes", [])
    best = None
    for g in gpus:
        lp = g.get("lowestPrice", {})
        bid = lp.get("minimumBidPrice")
        stock = lp.get("stockStatus")
        vram = g.get("memoryInGb", 0)
        if bid and stock and stock != "None" and vram >= 8:
            if best is None or bid < best[0]:
                best = (bid, vram, g.get("displayName","?"), g["id"], stock)
    if best and best[0] <= 0.15:
        region_results.append((dc_id, best))

region_results.sort(key=lambda x: x[1][0])
print(f"  {'Region':12s} {'$/hr':>6s} {'VRAM':>5s} {'GPU':35s} {'Stock'}")
print(f"  {'-'*12} {'-'*6} {'-'*5} {'-'*35} {'-'*6}")
for dc_id, (bid, vram, name, gid, stock) in region_results:
    marker = " ★" if dc_id == "EU-RO-1" else ""
    print(f"  {dc_id:12s} ${bid:.3f} {vram:4.0f}GB {name:35s} {stock}{marker}")

# Also show: for each High-stock GPU from global query, find which regions have it
print()
print("=" * 70)
print("HIGH-STOCK GPUs — which regions have them?")
print("=" * 70)

# Get global high-stock GPUs first
q_global = """query {
  gpuTypes {
    id displayName memoryInGb
    lowestPrice(input: { gpuCount: 1 }) {
      stockStatus minimumBidPrice
    }
  }
}"""
r_global = requests.post(url, json={"query": q_global}, timeout=15)
global_gpus = r_global.json().get("data", {}).get("gpuTypes", [])
high_stock_gpus = []
for g in global_gpus:
    lp = g.get("lowestPrice", {})
    if lp.get("stockStatus") == "High" and lp.get("minimumBidPrice") and g.get("memoryInGb", 0) >= 8:
        high_stock_gpus.append((lp["minimumBidPrice"], g.get("memoryInGb",0), g.get("displayName","?"), g["id"]))

high_stock_gpus.sort()
for _, vram, name, gid in high_stock_gpus[:5]:
    print(f"\n  {name} ({gid}) — {vram}GB — global High stock")
    # Check each region
    for dc in dcs:
        q = """query ($dc: String!, $gid: String!) {
          gpuType(input: { id: $gid }) {
            id displayName
            lowestPrice(input: { gpuCount: 1, dataCenterId: $dc }) {
              stockStatus minimumBidPrice
            }
          }
        }"""
        r = requests.post(url, json={"query": q, "variables": {"dc": dc["id"], "gid": gid}}, timeout=8)
        d = r.json()
        if "errors" in d:
            continue
        gt = d.get("data", {}).get("gpuType", {})
        if gt:
            lp = gt.get("lowestPrice", {})
            if lp.get("stockStatus") and lp["stockStatus"] != "None":
                bid = lp.get("minimumBidPrice", "?")
                stock = lp.get("stockStatus", "?")
                print(f"    {dc['id']:12s} ${bid}/hr  {stock}")
