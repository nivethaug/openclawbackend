"""Check specific pod status."""
import requests, json

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"

r = requests.post(url, json={"query": """query {
    myself { pods {
        id name desiredStatus imageName costPerHr gpuCount
        machine { gpuDisplayName location }
        runtime { uptimeInSeconds ports { privatePort publicPort ip } }
    }}
}"""}, headers={"Content-Type": "application/json"}, timeout=15)

data = r.json().get("data", {})
pods = data.get("myself", {}).get("pods", [])
print(f"Found {len(pods)} pods:\n")
for p in pods:
    print(f"  Pod: {p.get('name','?')} ({p['id']})")
    print(f"    Status:  {p.get('desiredStatus','?')}")
    print(f"    Image:   {p.get('imageName','?')}")
    print(f"    GPU:     {p.get('machine',{}).get('gpuDisplayName','?')}")
    print(f"    Cost:    ${p.get('costPerHr','?')}/hr")
    runtime = p.get("runtime") or {}
    uptime = runtime.get("uptimeInSeconds")
    print(f"    Uptime:  {uptime}s" if uptime else "    Uptime:  N/A")
    ports = runtime.get("ports") or []
    for port in ports:
        print(f"    Port:    {port.get('privatePort')} -> {port.get('publicPort')} @ {port.get('ip')}")
    print()
