import requests, os, json

api_key = os.environ.get('RUNPOD_API_KEY', '')
pod_id = '1cb096xro1o809'

# List my pods with runtime info
query = """
query {
  myself {
    pods {
      id name desiredStatus status
      runtime {
        ports { ip isIpPublic privatePort publicPort type }
      }
      machine {
        gpuDisplayName
      }
      containerDiskInGb
      imageName
    }
  }
}
"""

resp = requests.post('https://api.runpod.io/graphql',
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
    json={'query': query})
data = resp.json()

# Find our pod
pods = data.get('data', {}).get('myself', {}).get('pods', [])
for p in pods:
    print(f"Pod: {p['name']} ({p['id']})")
    print(f"  Status: {p['status']} / Desired: {p['desiredStatus']}")
    print(f"  Image: {p.get('imageName', 'N/A')}")
    print(f"  GPU: {p.get('machine', {}).get('gpuDisplayName', 'N/A')}")
    print(f"  Ports: {json.dumps(p.get('runtime', {}).get('ports', []), indent=4)}")
    print()
