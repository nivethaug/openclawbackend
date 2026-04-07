"""Detailed diagnostic of all start methods for spot pod. Send output to RunPod AI."""
import os
import requests
import json

API_KEY = os.environ.get("RUNPOD_API_KEY")
POD_ID = "olvdw1yjuoa1mz"

if not API_KEY:
    print("Set RUNPOD_API_KEY")
    exit(1)

def gql(query, variables=None, auth="query"):
    """Test both auth styles: query param and Bearer header."""
    results = {}
    for auth_style in ["query", "bearer"]:
        if auth_style == "query":
            url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
            headers = {"Content-Type": "application/json"}
        else:
            url = "https://api.runpod.io/graphql"
            headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=15)
            results[auth_style] = {
                "status_code": r.status_code,
                "response": r.json()
            }
        except Exception as e:
            results[auth_style] = {"error": str(e)}
    return results

print("=" * 70)
print("RUNPOD SPOT POD START DIAGNOSTIC")
print("=" * 70)
print(f"Pod ID: {POD_ID}")
print()

# 1. Check status
print("--- 1. CURRENT STATUS (pod query) ---")
status_q = """query($podId: String!) {
  pod(input: { podId: $podId }) {
    id name desiredStatus podType gpuCount costPerHr lastStatusChange
  }
}"""
r = gql(status_q, {"podId": POD_ID})
for auth, data in r.items():
    print(f"  Auth={auth}: {json.dumps(data, indent=2)[:300]}")
print()

# 2. Try podResume (on-demand style)
print("--- 2. podResume (on-demand resume) ---")
resume_q = """mutation($podId: String!) {
  podResume(input: { podId: $podId }) { id desiredStatus }
}"""
r = gql(resume_q, {"podId": POD_ID})
for auth, data in r.items():
    print(f"  Auth={auth}: {json.dumps(data, indent=2)[:400]}")
print()

# 3. Try podBidResume with $0.27
print("--- 3. podBidResume (spot resume, bid=$0.27) ---")
bid_q = """mutation($podId: String!, $bidPerGpu: Float!, $gpuCount: Int!) {
  podBidResume(input: { podId: $podId, bidPerGpu: $bidPerGpu, gpuCount: $gpuCount }) {
    id desiredStatus costPerHr
  }
}"""
r = gql(bid_q, {"podId": POD_ID, "bidPerGpu": 0.27, "gpuCount": 1})
for auth, data in r.items():
    print(f"  Auth={auth}: {json.dumps(data, indent=2)[:400]}")
print()

# 4. Try podBidResume with $0.40
print("--- 4. podBidResume (spot resume, bid=$0.40) ---")
r = gql(bid_q, {"podId": POD_ID, "bidPerGpu": 0.40, "gpuCount": 1})
for auth, data in r.items():
    print(f"  Auth={auth}: {json.dumps(data, indent=2)[:400]}")
print()

# 5. Try REST /v1/start (no body)
print("--- 5. REST /v1/pods/{id}/start (no body) ---")
try:
    r = requests.post(
        f"https://rest.runpod.io/v1/pods/{POD_ID}/start",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=15,
    )
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")
print()

# 6. Try REST /v1/start with bidPerGpu in body
print("--- 6. REST /v1/pods/{id}/start (body: {bidPerGpu: 0.30}) ---")
try:
    r = requests.post(
        f"https://rest.runpod.io/v1/pods/{POD_ID}/start",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"bidPerGpu": 0.30},
        timeout=15,
    )
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")
print()

# 7. Try podStop (should work or say already stopped)
print("--- 7. podStop (verify stop works) ---")
stop_q = """mutation($podId: String!) {
  podStop(input: { podId: $podId }) { id desiredStatus lastStatusChange }
}"""
r = gql(stop_q, {"podId": POD_ID})
for auth, data in r.items():
    print(f"  Auth={auth}: {json.dumps(data, indent=2)[:400]}")

print()
print("=" * 70)
print("END OF DIAGNOSTIC — send all output above to RunPod AI/support")
print("=" * 70)
