"""Test REST API to start pod."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
POD_ID = "olvdw1yjuoa1mz"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

print("1. Testing REST API: POST /v1/pods/{podId}/start")
url = f"https://rest.runpod.io/v1/pods/{POD_ID}/start"
resp = requests.post(url, headers=headers, timeout=15)
print(f"   Status: {resp.status_code}")
print(f"   Response: {json.dumps(resp.json(), indent=2)}")
import os
