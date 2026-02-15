#!/bin/bash
# infrastructure/build_image.sh - The "Brain + Muscle" builder

source "$(dirname "$0")/env_discovery.sh"
PROJECT_ROOT="$( dirname "$(dirname "$0")" )"

aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "🚀 Building Atomic Multi-Arch Image..."
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${IMAGE_URI}" \
  --provenance=false --push "${PROJECT_ROOT}"