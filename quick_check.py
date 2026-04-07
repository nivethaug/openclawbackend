import requests, os, json

api_key = os.environ.get('RUNPOD_API_KEY', '')
pod_id = '1cb096xro1o809'

# Check pod details
query = """
query {
  pod(id: "%s") {
    runtime {
      ports { ip isIpPublic privatePort publicPort type }
    }
    machine {
      gpuDisplayName
    }
  }
}
""" % pod_id

resp = requests.post('https://api.runpod.io/graphql',
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
    json={'query': query})
print("Pod details:", json.dumps(resp.json(), indent=2))

# Try health check
try:
    r = requests.get(f'https://{pod_id}-8000.proxy.runpod.net/health', timeout=5)
    print(f"\nHealth: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"\nHealth error: {e}")

# Try models endpoint
try:
    r = requests.get(f'https://{pod_id}-8000.proxy.runpod.net/v1/models', timeout=5)
    print(f"\nModels: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"\nModels error: {e}")

# Try root
try:
    r = requests.get(f'https://{pod_id}-8000.proxy.runpod.net/', timeout=5)
    print(f"\nRoot: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"\nRoot error: {e}")
