#!/bin/bash
# ─── GLM-4.7-Flash vLLM Startup Script ────────────────────
# Uses baked-in model if available, falls back to HF download.
# This runs inside the RunPod container.
# ────────────────────────────────────────────────────────────

set -e

MODEL_DIR="/app/models/glm-4.7-flash-4bit"
WORKSPACE_MODEL="/workspace/models/glm-4.7-flash-4bit"
FALLBACK_MODEL="zai-org/GLM-4.7-Flash"

# Determine which model path to use
MODEL_PATH=""
if [ -d "$MODEL_DIR" ] && [ -f "$MODEL_DIR/config.json" ]; then
    echo "✅ Using baked-in model at $MODEL_DIR"
    MODEL_PATH="$MODEL_DIR"
elif [ -d "$WORKSPACE_MODEL" ] && [ -f "$WORKSPACE_MODEL/config.json" ]; then
    echo "✅ Using workspace model at $WORKSPACE_MODEL (network volume)"
    MODEL_PATH="$WORKSPACE_MODEL"
else
    echo "⚠️ No local model found. Downloading from HuggingFace..."
    echo "   This adds ~2-3 minutes to first startup."
    pip install -q huggingface_hub
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${FALLBACK_MODEL}', revision='gptq-4bit',
                  local_dir='${MODEL_DIR}', local_dir_use_symlinks=False)
print('✅ Download complete')
"
    MODEL_PATH="$MODEL_DIR"
fi

echo "🚀 Starting vLLM with model: $MODEL_PATH"
echo "   Quantization: gptq_marlin"
echo "   Max model len: 4096"
echo "   GPU memory utilization: 0.92"
echo ""

exec python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --quantization gptq_marlin \
    --tensor-parallel-size 1 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.92 \
    --host 0.0.0.0 \
    --port 8000 \
    --trust-remote-code
