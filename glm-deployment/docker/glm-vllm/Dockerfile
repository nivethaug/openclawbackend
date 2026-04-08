# GLM-4.7-Flash GPTQ 4-bit - vLLM Docker Image
# Pre-bakes the model + vLLM with transformers 5.x (required for glm4_moe_lite)
#
# Why NOT use vllm/vllm-openai base image:
#   vLLM pip requires transformers<5, but GLM-4.7-Flash needs transformers>=5.1.0
#   So we install vLLM from pip (0.19.0) + force transformers 5.x on top.
#   The --trust-remote-code flag lets vLLM handle the glm4_moe_lite architecture.
#
# Image size: ~20GB (vllm ~10GB + model ~16GB)

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Install vLLM + transformers 5.x in one shot
# vLLM 0.19.0 requires transformers<5, but we override with 5.x after
# This works because glm4_moe_lite support is in transformers, not vLLM core
RUN pip3 install --no-cache-dir vllm==0.19.0 && \
    pip3 install --no-cache-dir 'transformers>=5.1.0'

# Download the GPTQ-4bit model from HuggingFace (~16GB, ungated)
RUN pip3 install --no-cache-dir huggingface_hub
RUN mkdir -p /opt/glm-model
COPY download_model.py /tmp/download_model.py
RUN python3 /tmp/download_model.py 2>&1 && rm -rf /tmp/hf_cache || { echo "Download failed"; exit 1; }

# Verify model config exists
RUN test -f /opt/glm-model/config.json && echo "Model ready at /opt/glm-model" || { echo "Model files not found"; exit 1; }

EXPOSE 8000

# vLLM OpenAI-compatible server
ENTRYPOINT ["vllm", "serve", "/opt/glm-model"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--tensor-parallel-size", "1", "--max-model-len", "4096", "--gpu-memory-utilization", "0.92", "--trust-remote-code"]
