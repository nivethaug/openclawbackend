"""Quick introspection test."""
import os, requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
h = {"Content-Type": "application/json"}

# Test 1: Simple __schema
print("Test 1: __schema introspection...")
r = requests.post(url, json={"query": "{ __schema { mutationType { fields { name } } } }"}, headers=h, timeout=30)
print(f"  Status: {r.status_code}")
print(f"  Body: {r.text[:500]}")

# Test 2: __type lookup
print("\nTest 2: __type(PodFindAndDeployOnDemandInput)...")
r2 = requests.post(url, json={"query": '{ __type(name: "PodFindAndDeployOnDemandInput") { name kind inputFields { name type { kind name ofType { kind name } } } } }'}, headers=h, timeout=30)
print(f"  Status: {r2.status_code}")
print(f"  Body: {r2.text[:1000]}")

# Test 3: Try PodCreateInput
print("\nTest 3: __type(PodCreateInput)...")
r3 = requests.post(url, json={"query": '{ __type(name: "PodCreateInput") { name kind inputFields { name type { kind name ofType { kind name } } } } }'}, headers=h, timeout=30)
print(f"  Status: {r3.status_code}")
print(f"  Body: {r3.text[:1000]}")

# Test 4: Try CreatePodInput
print("\nTest 4: __type(CreatePodInput)...")
r4 = requests.post(url, json={"query": '{ __type(name: "CreatePodInput") { name kind inputFields { name type { kind name ofType { kind name } } } } }'}, headers=h, timeout=30)
print(f"  Status: {r4.status_code}")
print(f"  Body: {r4.text[:1000]}")
