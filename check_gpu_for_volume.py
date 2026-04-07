"""Find GPUs compatible with your network volume's data center.

Uses RunPod GraphQL dataCenters query (discovered from runpodctl source)
and myself.networkVolumes to cross-reference availability.
"""
import os
import requests
import json

API_KEY = os.environ.get("RUNPOD_API_KEY")
if not API_KEY:
    print("Set RUNPOD_API_KEY")
    exit(1)

url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
headers = {"Content-Type": "application/json"}

def gql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    data = r.json()
    if "errors" in data:
        print(f"GraphQL Error: {data['errors'][0].get('message', '?')}")
        return None
    return data.get("data", {})

# ── Step 1: Get network volumes ──
print("=" * 65)
print("STEP 1: YOUR NETWORK VOLUMES")
print("=" * 65)
data = gql("""
query {
  myself {
    networkVolumes {
      id
      name
      size
      dataCenterId
    }
  }
}
""")
if not data:
    exit(1)

volumes = data.get("myself", {}).get("networkVolumes", [])
if not volumes:
    print("  No network volumes found!")
    exit(1)

vol_dc = None
for v in volumes:
    print(f"  Volume:  {v.get('name', '?')} ({v['id']})")
    print(f"  Size:    {v.get('size', '?')} GB")
    print(f"  DC:      {v.get('dataCenterId', '?')}")
    vol_dc = v.get("dataCenterId")
    print()

if not vol_dc:
    print("  ERROR: Could not determine data center from volume!")
    exit(1)

# ── Step 2: Get all data centers with GPU availability ──
print("=" * 65)
print(f"STEP 2: GPU AVAILABILITY IN {vol_dc}")
print("=" * 65)
data = gql("""
query {
  dataCenters {
    id
    name
    location
    gpuAvailability {
      gpuTypeId
      displayName
      stockStatus
    }
  }
}
""")
if not data:
    exit(1)

dcs = data.get("dataCenters", [])

# Find our DC and show GPUs there
target_dc = None
all_dc_names = {}
for dc in dcs:
    all_dc_names[dc["id"]] = f"{dc.get('name', '?')} ({dc.get('location', '?')})"
    if dc["id"] == vol_dc:
        target_dc = dc

if target_dc:
    gpus = target_dc.get("gpuAvailability", [])
    print(f"  Data Center: {target_dc.get('name', '?')} ({target_dc.get('location', '?')})")
    print(f"  Total GPU types available: {len(gpus)}")
    print()
    
    # Sort by stock status (High first, then Medium, Low)
    stock_order = {"High": 0, "Medium": 1, "Low": 2, "None": 3}
    gpus_sorted = sorted(gpus, key=lambda g: stock_order.get(g.get("stockStatus", "None"), 9))
    
    print(f"  {'GPU':45s}  {'Stock':8s}  {'ID'}")
    print(f"  {'-'*45}  {'-'*8}  {'-'*25}")
    for g in gpus_sorted:
        stock = g.get("stockStatus") or "None"
        gid = g.get("gpuTypeId") or "?"
        dname = g.get("displayName") or gid
        if stock != "None":
            print(f"  {dname:45s}  {stock:8s}  {gid}")
    
    # Show what's NOT available too
    print()
    print(f"  --- Out of stock in {vol_dc} ---")
    for g in gpus_sorted:
        stock = g.get("stockStatus") or "None"
        gid = g.get("gpuTypeId") or "?"
        dname = g.get("displayName") or gid
        if stock == "None":
            print(f"  {dname:45s}  {stock:8s}  {gid}")
else:
    print(f"  WARNING: Data center {vol_dc} not found in dataCenters query!")
    print(f"  Available DCs: {list(all_dc_names.keys())}")

# ── Step 3: Get pricing for GPUs in our DC ──
print()
print("=" * 65)
print(f"STEP 3: SPOT PRICING IN {vol_dc}")
print("=" * 65)

# Query gpuTypes with lowestPrice filtered by our DC
data = gql("""
query {
  gpuTypes {
    id displayName memoryInGb
    lowestPrice(input: { gpuCount: 1 }) {
      stockStatus
      minimumBidPrice
      uninterruptablePrice
    }
  }
}
""")
if not data:
    exit(1)

all_gpus = {g["id"]: g for g in data.get("gpuTypes", [])}

if target_dc:
    print(f"\n  {'$/hr spot':>10s}  {'$/hr O/D':>10s}  {'VRAM':>6s}  {'Stock':8s}  {'GPU'}")
    print(f"  {'-'*10}  {'-'*10}  {'-'*6}  {'-'*8}  {'-'*45}")
    
    results = []
    for g in target_dc.get("gpuAvailability", []):
        stock = g.get("stockStatus") or "None"
        if stock == "None":
            continue
        gid = g.get("gpuTypeId") or ""
        gpu_info = all_gpus.get(gid, {})
        lp = gpu_info.get("lowestPrice") or {}
        bid = lp.get("minimumBidPrice") or 999
        od = lp.get("uninterruptablePrice") or 999
        vram = gpu_info.get("memoryInGb") or 0
        name = g.get("displayName") or gpu_info.get("displayName") or gid
        results.append((bid, od, vram, stock, name, gid))
    
    results.sort()
    for bid, od, vram, stock, name, gid in results:
        print(f"  ${bid:>8.3f}  ${od:>8.3f}  {vram:>4.0f}GB  {stock:8s}  {name}")
    
    # Highlight best options for GLM-4.7-Flash (needs ~6GB VRAM)
    print()
    print("=" * 65)
    print("BEST OPTIONS FOR GLM-4.7-FLASH (>=8GB VRAM, in stock)")
    print("=" * 65)
    good = [(bid, od, vram, stock, name, gid) for bid, od, vram, stock, name, gid in results if vram >= 8]
    if good:
        for bid, od, vram, stock, name, gid in good:
            emoji = "⭐" if bid < 0.15 else ("✅" if bid < 0.25 else "💰")
            print(f"  {emoji} ${bid:.3f}/hr  {vram:.0f}GB  {stock:8s}  {name}  ({gid})")
    else:
        print("  No GPUs with >= 8GB VRAM currently in stock!")

# ── Step 4: Show ALL data centers with good GPU availability ──
print()
print("=" * 65)
print("STEP 4: ALL DATA CENTERS — BEST CHEAP GPU PER DC")
print("=" * 65)
print("  (in case you want to recreate your volume elsewhere)")
print()

dc_results = []
for dc in dcs:
    gpus_avail = dc.get("gpuAvailability", [])
    best = None
    for g in gpus_avail:
        stock = g.get("stockStatus") or "None"
        if stock == "None":
            continue
        gid = g.get("gpuTypeId") or ""
        gpu_info = all_gpus.get(gid, {})
        lp = gpu_info.get("lowestPrice") or {}
        bid = lp.get("minimumBidPrice") or 999
        vram = gpu_info.get("memoryInGb") or 0
        name = g.get("displayName") or gpu_info.get("displayName") or gid
        if vram >= 8 and (best is None or bid < best[0]):
            best = (bid, vram, stock, name, gid)
    if best:
        dc_results.append((best[0], dc.get("name") or "?", dc.get("location") or "?", dc["id"], best))

dc_results.sort()
print(f"  {'$/hr':>6s}  {'Stock':8s}  {'GPU':35s}  {'Data Center'}")
print(f"  {'-'*6}  {'-'*8}  {'-'*35}  {'-'*40}")
for bid, dc_name, dc_loc, dc_id, (price, vram, stock, name, gid) in dc_results[:20]:
    marker = " ◄ YOUR VOLUME" if dc_id == vol_dc else ""
    print(f"  ${bid:.3f}  {stock:8s}  {name:35s}  {dc_name} ({dc_loc}){marker}")
