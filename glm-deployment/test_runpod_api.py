"""Test RunPod GraphQL API to find correct start/stop mutations."""
import os
import requests, json
import os

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
POD_ID = "olvdw1yjuoa1mz"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Try podResume (resume a stopped pod)
print("Trying podResume (minimal)...")
r = requests.post("https://api.runpod.io/graphql", json={
    "query": 'mutation { podResume(input: { podId: "' + POD_ID + '" }) { id desiredStatus } }'
}, headers=HEADERS)
print(json.dumps(r.json(), indent=2))
print(json.dumps(r.json(), indent=2))
import os
