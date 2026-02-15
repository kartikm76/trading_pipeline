#!/bin/bash
# infrastructure/build_image.sh - Full Docker image lifecycle
#
# Builds the image, pushes to ECR, then updates the EMR Serverless
# application to use the new image (stop → update → restart).
#
# Usage:
#   ./infrastructure/build_image.sh              # Build, push, and update EMR app
#   ./infrastructure/build_image.sh --build-only # Build and push only (skip EMR update)

SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/env_discovery.sh"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"

# ── Step 1: Build & Push ──
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "🚀 Building Multi-Arch Image..."
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${IMAGE_URI}" \
  --provenance=false --push "${PROJECT_ROOT}"

if [ $? -ne 0 ]; then
    echo "❌ Image build failed"
    exit 1
fi
echo "✅ Image pushed: $IMAGE_URI"

# ── Step 2: Update EMR Application (unless --build-only) ──
if [ "$1" == "--build-only" ]; then
    echo "ℹ️  Skipping EMR app update (--build-only)"
    exit 0
fi

if [ -z "$APP_ID" ]; then
    echo "⚠️  No application ID found — skipping EMR app update."
    echo "   Run setup to create an EMR application first."
    exit 0
fi

echo "🔄 Updating EMR Application: $APP_ID with image: $IMAGE_URI"

# Stop if running
APP_STATE=$(aws emr-serverless get-application --application-id "$APP_ID" --query 'application.state' --output text)
if [ "$APP_STATE" == "STARTED" ]; then
    echo "⏸️  Stopping application..."
    aws emr-serverless stop-application --application-id "$APP_ID"
    while true; do
        APP_STATE=$(aws emr-serverless get-application --application-id "$APP_ID" --query 'application.state' --output text)
        [ "$APP_STATE" == "STOPPED" ] && break
        echo "   State: $APP_STATE"
        sleep 5
    done
    echo "✅ Application stopped"
fi

# Update image
aws emr-serverless update-application \
  --application-id "$APP_ID" \
  --image-configuration "{\"imageUri\": \"${IMAGE_URI}\"}"

if [ $? -ne 0 ]; then
    echo "❌ Failed to update application"
    exit 1
fi

# Restart
echo "▶️  Starting application..."
aws emr-serverless start-application --application-id "$APP_ID"
while true; do
    APP_STATE=$(aws emr-serverless get-application --application-id "$APP_ID" --query 'application.state' --output text)
    [ "$APP_STATE" == "STARTED" ] && break
    echo "   State: $APP_STATE"
    sleep 5
done
echo "✅ Application updated and ready!"