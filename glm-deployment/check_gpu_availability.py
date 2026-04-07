"""Check GPU availability via RunPod GraphQL gpuTypes query.

Usage: python check_gpu_availability.py [gpu_name_filter]
  e.g. python check_gpu_availability.py 3090
"""
import os
import sys
import requests
import json

API_KEY = os.environ.get("RUNPOD_API_KEY")
if not API_KEY:
    print("Set RUNPOD_API_KEY")
    exit(1)

url = f"https://api.runpod.io/graphql?api_key={API_KEY}"

# Query all GPU types with pricing, stock, and per-region availability
query = """query {
  gpuTypes {
    id displayName memoryInGb
    lowestPrice(input: { gpuCount: 1 }) {
      stockStatus
      availableGpuCounts
      minimumBidPrice
      uninterruptablePrice
    }
  }
}"""

r = requests.post(url, json={"query": query}, headers={"Content-Type": "application/json"}, timeout=15)
data = r.json()

if "errors" in data:
    print(f"Error: {data['errors']}")
    exit(1)

gpus = data.get("data", {}).get("gpuTypes", [])

# Optional: filter by name from CLI arg
name_filter = sys.argv[1].lower() if len(sys.argv) > 1 else None

# ── Show RTX A4500 specifically ──
print("=" * 60)
print("RTX A4500 / PRO 4500 AVAILABILITY")
print("=" * 60)
for g in gpus:
    name = g.get("displayName", "")
    if "4500" in name.upper():
        lp = g.get("lowestPrice", {})
        locs = g.get("locations", [])
        print(f"  GPU ID:    {g['id']}")
        print(f"  Name:      {name}")
        print(f"  VRAM:      {g.get('memoryInGb', '?')} GB")
        print(f"  Stock:     {lp.get('stockStatus', '?')}")
        print(f"  Available: {lp.get('availableGpuCounts', '?')}")
        print(f"  Spot:      ${lp.get('minimumBidPrice', '?')}/hr")
        print(f"  On-demand: ${lp.get('uninterruptablePrice', '?')}/hr")
        print()
        break

# ── Best candidates for GLM-4.7-Flash (needs ~6GB VRAM for 4-bit) ──
print("=" * 60)
print("BEST GPUs FOR GLM-4.7-FLASH (>=8GB VRAM, spot < $0.30/hr)")
print("=" * 60)
candidates = []
for g in gpus:
    lp = g.get("lowestPrice", {})
    bid = lp.get("minimumBidPrice", 999)
    vram = g.get("memoryInGb", 0)
    stock = lp.get("stockStatus", "None")
    # Must have >= 8GB VRAM, price < $0.30, and actual stock
    if bid and bid < 0.30 and vram >= 8 and stock not in ("None", None):
        candidates.append((bid, vram, g.get("displayName", "?"), g["id"], stock))

candidates.sort()
print(f"  {'$/hr':>6s}  {'VRAM':>5s}  {'Name':40s}  {'Stock':6s}")
print(f"  {'-'*6}  {'-'*5}  {'-'*40}  {'-'*6}")
for bid, vram, name, gid, stock in candidates[:15]:
    print(f"  ${bid:.3f}  {vram:4.0f}GB  {name:40s}  {stock:6s}")

# ── All GPUs with stock sorted by price ──
print()
print("=" * 60)
print("ALL GPUs WITH STOCK (sorted by spot price, top 20)")
print("=" * 60)
all_stock = []
for g in gpus:
    lp = g.get("lowestPrice", {})
    bid = lp.get("minimumBidPrice")
    if bid and lp.get("stockStatus") not in ("None", None):
        all_stock.append((bid, g.get("memoryInGb", 0), g.get("displayName", "?"), g["id"], lp.get("stockStatus", "?")))

all_stock.sort()
print(f"  {'$/hr':>6s}  {'VRAM':>5s}  {'Name':45s}  {'Stock':6s}")
print(f"  {'-'*6}  {'-'*5}  {'-'*45}  {'-'*6}")
for bid, vram, name, gid, stock in all_stock[:20]:
    print(f"  ${bid:.3f}  {vram:4.0f}GB  {name:45s}  {stock}")

# ── Name filter: show details for matching GPU ──
if name_filter:
    print()
    print("=" * 60)
    print(f"FILTER: '{name_filter}' — detailed results")
    print("=" * 60)
    for g in gpus:
        if name_filter in g.get("displayName", "").lower() or name_filter in g.get("id", "").lower():
            lp = g.get("lowestPrice", {})
            locs = g.get("locations", [])
            print(f"\n  ID:         {g['id']}")
            print(f"  Name:       {g.get('displayName', '?')}")
            print(f"  VRAM:       {g.get('memoryInGb', '?')} GB")
            print(f"  Stock:      {lp.get('stockStatus', '?')}")
            print(f"  Spot:       ${lp.get('minimumBidPrice', '?')}/hr")
            print(f"  On-demand:  ${lp.get('uninterruptablePrice', '?')}/hr")
            if locs:
                print(f"  Regions ({len(locs)}):")
                for loc in locs:
                    print(f"    {loc.get('name', '?'):35s}  GPUs: {loc.get('gpuCount', '?')}")
            print()
