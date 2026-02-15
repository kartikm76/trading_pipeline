#!/bin/bash
# infrastructure/env_discovery.sh

# 1. Identity Discovery
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text | tr -d '[:space:]')
export AWS_REGION=$(aws configure get region | tr -d '[:space:]')
export REPO_NAME="trading-pipeline"

# 2. Reconstruct the FULL URI (Zero hidden spaces)
export IMAGE_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"
export IMAGE_URI="${IMAGE_URL}:latest"

# 3. App Metadata
INFRA_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export APP_ID=$(cat "$(dirname "$INFRA_DIR")/.application-id" 2>/dev/null | tr -d '[:space:]')
export ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/EMRServerlessRole"