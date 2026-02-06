#!/bin/bash
set -e

export ENV=${1:-dev}
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="$ROOT_DIR/infrastructure/2_deploy_and_submit.sh"

echo "🏁 Starting Batch Controller [Env: $ENV]"

# PHASE 1: Deploy Artifacts Once
if [ "$ENV" == "prod" ]; then
    echo "🏗️  Deploying Code..."
    bash "$DEPLOY_SCRIPT" "deploy-only"
fi

# PHASE 2: Loop (Data move -> Submit -> Archive)
MODE="bootstrap"
while true; do
    # 1. Check/Get Batch
    # (Using your existing S3 ls logic here)
    FILES=$(aws s3 ls s3://trading-pipeline/data/raw/landing/ | grep ".csv" | awk '{print $4}' | head -n 15)

    if [ -z "$FILES" ]; then break; fi

    # 2. Move to Staging
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline/data/raw/landing/$F" "s3://trading-pipeline/data/raw/staging/$F"
    done

    # 3. Submit (Skip Upload because Phase 1 did it)
    if [ "$ENV" == "prod" ]; then
        bash "$DEPLOY_SCRIPT" "$MODE" "true"
    else
        ENV=$ENV python3 src/main.py --$MODE
    fi

    # 4. Archive
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline/data/raw/staging/$F" "s3://trading-pipeline/data/raw/processed/$F"
    done
    MODE="daily"
done