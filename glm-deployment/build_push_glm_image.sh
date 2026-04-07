#!/bin/bash
# ─── Build & Push GLM vLLM Docker Image ───────────────────
# Builds the custom image with model baked in and pushes to Docker Hub.
#
# Prerequisites:
#   1. Docker Desktop running with BuildKit enabled
#   2. docker login completed
#   3. Set DOCKER_USER env var (or edit below)
#
# Usage:
#   chmod +x build_push_glm_image.sh
#   DOCKER_USER=myuser ./build_push_glm_image.sh
#
# The build downloads ~5GB model data. Takes 5-15 min depending on bandwidth.
# ──────────────────────────────────────────────────────────

set -e

DOCKER_USER="${DOCKER_USER:-nivet}"  # <-- change this
IMAGE_NAME="glm-vllm"
TAG="4.7-flash-4bit"
FULL_TAG="${DOCKER_USER}/${IMAGE_NAME}:${TAG}"

echo "╔══════════════════════════════════════════════════╗"
echo "║  Building GLM-4.7-Flash vLLM Docker Image       ║"
echo "║  Image: ${FULL_TAG}"
echo "║  This will download ~5GB model weights           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Build with BuildKit for caching
DOCKER_BUILDKIT=1 docker build \
    -t "${FULL_TAG}" \
    -t "${DOCKER_USER}/${IMAGE_NAME}:latest" \
    -f Dockerfile.glm \
    .

echo ""
echo "✅ Build complete!"
echo ""

# Show image size
docker images "${FULL_TAG}" --format "Image size: {{.Size}}"

echo ""
echo "🔄 Pushing to Docker Hub..."
docker push "${FULL_TAG}"
docker push "${DOCKER_USER}/${IMAGE_NAME}:latest"

echo ""
echo "✅ Done! Image available at:"
echo "   ${FULL_TAG}"
echo ""
echo "Update your deploy scripts to use:"
echo "   IMAGE = \"${FULL_TAG}\""
