"""Test RunPod REST API to start a spot pod."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
POD_ID = "olvdw1yjuoa1mz"
HEADERS = {"Authorization": API_KEY, "Content-Type": "application/json"}

# Try REST API - start pod
print("Trying REST API: POST /v2/pods/{id}/start...")
r = requests.post(f"https://api.runpod.io/v2/pods/{POD_ID}/start", headers=HEADERS)
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2) if r.text else "No response body")
import os
