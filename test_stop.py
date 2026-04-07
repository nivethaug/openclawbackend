"""Quick test of podStop mutation."""
import os
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

mutation = """
mutation StopPod($podId: String!) {
    podStop(input: {podId: $podId}) {
        id
        desiredStatus
        lastStatusChange
    }
}
"""
variables = {"podId": "olvdw1yjuoa1mz"}
resp = requests.post("https://api.runpod.io/graphql", json={"query": mutation, "variables": variables}, headers=headers, timeout=10)
print(json.dumps(resp.json(), indent=2))
import os
