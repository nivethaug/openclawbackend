#!/bin/bash
# ============================================================
# RunPod GLM-4-9B One-Time Setup Script
# ============================================================
# Run this ONCE on a fresh pod with a mounted Network Volume.
# It installs everything to /workspace so it persists across restarts.
#
# Usage:
#   bash /workspace/setup_glm.sh
# ============================================================

set -e

echo "============================================"
echo "GLM-4-9B Setup - Installing to Network Volume"
echo "============================================"

# 1. Install pip packages to Network Volume
echo ""
echo "[1/4] Installing Python packages to /workspace/pip-packages..."
mkdir -p /workspace/pip-packages
pip install --target /workspace/pip-packages \
    vllm \
    transformers \
    accelerate \
    sentencepiece \
    tiktoken \
    2>&1 | tail -5

echo "✅ Packages installed to /workspace/pip-packages"

# 2. Download model to Network Volume
echo ""
echo "[2/4] Downloading GLM-4-9B-Chat to /workspace/models/glm-4-9b-chat..."
mkdir -p /workspace/models
pip install huggingface_hub
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='THUDM/glm-4-9b-chat',
    local_dir='/workspace/models/glm-4-9b-chat',
    local_dir_use_symlinks=False
)
print('✅ Model downloaded!')
"

# 3. Verify model files
echo ""
echo "[3/4] Verifying model files..."
if [ -f "/workspace/models/glm-4-9b-chat/config.json" ]; then
    echo "✅ config.json found"
else
    echo "❌ config.json NOT found - download may have failed"
    exit 1
fi

MODEL_SIZE=$(du -sh /workspace/models/glm-4-9b-chat/ | cut -f1)
echo "   Model size: $MODEL_SIZE"

# 4. Create the auto-start script
echo ""
echo "[4/4] Creating auto-start script..."
cat > /workspace/start_glm.sh << 'STARTSCRIPT'
#!/bin/bash
# GLM-4-9B Auto-Start Script
# Add this as your pod's Start Command: bash /workspace/start_glm.sh

export PYTHONPATH=/workspace/pip-packages:$PYTHONPATH
export PATH=/workspace/pip-packages/bin:$PATH

echo "Starting GLM-4-9B server..."
python -m vllm.entrypoints.openai.api_server \
    --model /workspace/models/glm-4-9b-chat \
    --trust-remote-code \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --host 0.0.0.0 \
    --port 8000
STARTSCRIPT

chmod +x /workspace/start_glm.sh
echo "✅ Created /workspace/start_glm.sh"

# Done!
echo ""
echo "============================================"
echo "SETUP COMPLETE! ✅"
echo "============================================"
echo ""
echo "Everything is installed on the Network Volume."
echo "Files on /workspace:"
du -sh /workspace/* 2>/dev/null
echo ""
echo "To start the server now, run:"
echo "  bash /workspace/start_glm.sh"
echo ""
echo "For future pods, set as Start Command:"
echo "  bash /workspace/start_glm.sh"
echo ""
echo "Make sure to expose HTTP port: 8000"
echo "============================================"
