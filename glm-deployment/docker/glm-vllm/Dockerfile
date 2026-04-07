# GLM-4.7-Flash GPTQ 4-bit - vLLM Docker Image
# Pre-bakes the model + latest transformers into the image
# Eliminates: HF download time, transformers version mismatch, speculator crash
#
# Steps:
#   1. cd d:\openclawbackend\docker\glm-vllm
#   2. docker login
#   3. docker build -t YOURUSER/glm-vllm:4.7-flash-4bit .
#   4. docker push YOURUSER/glm-vllm:4.7-flash-4bit
#   5. Set env GLM_IMAGE=YOURUSER/glm-vllm:4.7-flash-4bit
#   6. python deploy_glm.py deploy
#
# Image size: ~20GB (base vllm ~10GB + model ~16GB)

FROM vllm/vllm-openai:latest

# Install git (required for pip install from git URLs)
RUN apt-get update && apt-get install -y --no-install-recommends git

# Upgrade to transformers 5.x (required for glm4_moe_lite architecture)
RUN pip install --no-cache-dir 'git+https://github.com/huggingface/transformers.git'

# Pre-download the GPTQ-4bit model from HuggingFace (~16GB)
# Model is ungated - no HF_TOKEN needed
RUN pip install --no-cache-dir huggingface_hub
RUN mkdir -p /opt/glm-model
COPY download_model.py /tmp/download_model.py
RUN python3 /tmp/download_model.py && rm -rf /tmp/hf_cache

# Verify model config exists
RUN test -f /opt/glm-model/config.json && echo "Model ready at /opt/glm-model"

# Default vLLM entrypoint args (override via RunPod dockerArgs)
CMD ["--model", "/opt/glm-model", "--tensor-parallel-size", "1", "--max-model-len", "4096", "--gpu-memory-utilization", "0.92", "--host", "0.0.0.0", "--port", "8000", "--trust-remote-code"]
