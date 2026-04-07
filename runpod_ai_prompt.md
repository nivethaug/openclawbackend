# RunPod AI Prompt — Copy/Paste Into RunPod AI Chat

---

## What I Have

- **Network Volume**: `s56scam7ck` (65GB) in data center **EU-RO-1**, mounted at `/workspace`
- **Model weights**: `/workspace/models/glm-4.7-flash-4bit` (GLM-4.7-Flash 31B MoE, GPTQ 4-bit, ~6GB VRAM)
- **Docker image**: `vllm/vllm-openai:latest`
- **Goal**: Programmatically start/stop a GPU pod with this volume attached, minimizing cost (prefer spot pricing)

## What I've Tried and the Exact Errors

### Attempt 1: `podFindAndDeployOnDemand` with `interruptible: true`

You previously told me to add `interruptible: true` to the input. It fails:

```graphql
mutation deploy($inp: PodFindAndDeployOnDemandInput!) {
    podFindAndDeployOnDemand(input: $inp) {
        id name desiredStatus costPerHr
    }
}
```

Variables:
```json
{
    "cloudType": "COMMUNITY",
    "gpuCount": 1,
    "gpuTypeId": "NVIDIA GeForce RTX 4090",
    "imageName": "vllm/vllm-openai:latest",
    "containerDiskInGb": 20,
    "dockerArgs": "--model /workspace/models/glm-4.7-flash-4bit --quantization gptq_marlin --host 0.0.0.0 --port 8000",
    "ports": "8000/http,22/tcp",
    "minMemoryInGb": 15,
    "minVcpuCount": 4,
    "networkVolumeId": "s56scam7ck",
    "volumeMountPath": "/workspace",
    "interruptible": true
}
```

**Error**: Field not recognized / no effect — still creates on-demand pods.

### Attempt 2: `podFindAndDeployOnDemand` WITHOUT `interruptible` — no capacity

Same mutation, removing `interruptible`. Tried these GPU types in EU-RO-1:
- `NVIDIA RTX 4000 Ada Generation`
- `NVIDIA GeForce RTX 4090`
- `NVIDIA RTX PRO 4500 Blackwell`
- `NVIDIA GeForce RTX 5090`
- `NVIDIA A100-SXM4-80GB`

Tried with `cloudType`: `"COMMUNITY"`, `"SECURE"`, `"ALL"`.

**Error for ALL combinations**: `"The chosen GPU is no longer available. Please choose another GPU type or cloud type."`

### Attempt 3: `podBidResume` on existing stopped pod

```graphql
mutation resume($pid: String!, $bid: Float!, $gpus: Int!) {
    podBidResume(input: {podId: $pid, bidPerGpu: $bid, gpuCount: $gpus}) {
        id desiredStatus costPerHr
    }
}
```

Tried bids from $0.10 up to $0.30 per GPU/hr.

**Error**: `"Insufficient capacity to fulfill your request"` or `"not enough GPUs"`

### Attempt 4: Wide search across ALL data centers

I queried `dataCenters { gpuAvailability { gpuTypeId stockStatus } }` and found GPUs with "Low" or "Medium" stock in various DCs. Then tried `podFindAndDeployOnDemand` with `dataCenterId` set to each DC that had stock.

**Tried**: EU-RO-1, EU-CZ-1, EUR-IS-2, US-IL-1, US-NC-1, US-TX-3 and more.

**Error for ALL**: Same "no longer available" error, even for GPUs showing "Medium" stock.

## What I Confirmed from runpodctl Source Code

I examined the RunPod runpodctl Go source code on GitHub and found:

1. `CreatePodInput` struct has **NO `interruptible` field** — only: `cloudType`, `containerDiskInGb`, `deployCost`, `dockerArgs`, `env`, `gpuCount`, `gpuTypeId`, `imageName`, `minMemoryInGb`, `minVcpuCount`, `name`, `networkVolumeId`, `ports`, `startSsh`, `supportPublicIp`, `volumeMountPath`, `dataCenterId`
2. The `podFindAndDeployOnDemand` mutation always creates ON-DEMAND pods
3. `podBidResume` is the ONLY way to get spot pricing, but it only works on existing stopped pods
4. Cloud types are only `"COMMUNITY"`, `"SECURE"`, `"ALL"` — no `"SPOT"` or `"INTERRUPTABLE"`

## My Questions

**Q1**: Is there ANY way to programmatically create a new SPOT (interruptible) pod via the API? Or is the only path: create on-demand → stop → `podBidResume`?

**Q2**: When `podBidResume` fails with "not enough GPUs", but the `dataCenters` query shows "Medium" stock for that GPU type in that DC — what's happening? Is the stock indicator unreliable?

**Q3**: What is the exact API flow for a cost-minimized pod lifecycle with a network volume? Specifically:
- Step 1: Create pod (how? on-demand? can it be spot?)
- Step 2: Stop pod when not needed (stop billing)
- Step 3: Resume pod later (spot price via `podBidResume`?)
- Step 4: If resume fails, what then? Delete and recreate?

**Q4**: Is the global GPU capacity issue I'm hitting (all DCs failing) a temporary condition? Or is there a way to reliably get capacity — like SECURE cloud being more available than COMMUNITY?

**Q5**: Can you give me **working Python code** that implements this full lifecycle — create with volume, stop, resume at spot price, handle failures? I need actual tested code, not theoretical descriptions.

Questions:
1. How do I create a NEW spot/interruptible pod via API with a network volume attached?
2. Is there a spot equivalent of podFindAndDeployOnDemand?
3. What does "Medium" stock mean in the dataCenters query if I can't actually allocate GPUs?
4. Can I specify dataCenterId in PodFindAndDeployOnDemandInput to match my volume's DC?
```
