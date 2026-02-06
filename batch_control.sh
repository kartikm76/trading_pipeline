#!/bin/bash
set -e

export ENV=${1:-dev}
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="$ROOT_DIR/infrastructure/2_deploy_and_submit.sh"

# Timestamp function for logging
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $1"; }

log "🏁 Starting Batch Controller [Env: $ENV]"

# PHASE 1: Deploy Artifacts Once
if [ "$ENV" == "prod" ]; then
    log "🏗️  Deploying Code..."
    bash "$DEPLOY_SCRIPT" "deploy-only"
fi

# PHASE 2: Loop (Data move -> Submit -> Archive)
MODE="bootstrap"
BATCH_NUM=1
while true; do
    # 1. Check/Get Batch
    log "📋 Checking for files in landing zone..."
    FILES=$(aws s3 ls s3://trading-pipeline/data/raw/landing/ | grep ".csv" | awk '{print $4}' | head -n 15)

    if [ -z "$FILES" ]; then
        log "✅ No more files to process. Batch controller complete."
        break
    fi

    FILE_COUNT=$(echo "$FILES" | wc -l | tr -d ' ')
    log "📦 Batch #$BATCH_NUM: Found $FILE_COUNT files to process in $MODE mode"

    # 2. Move to Staging
    log "📁 Moving files from landing → staging..."
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline/data/raw/landing/$F" "s3://trading-pipeline/data/raw/staging/$F"
    done
    log "✅ Files moved to staging"

    # 3. Submit (Skip Upload because Phase 1 did it)
    log "🚀 Submitting Spark job in $MODE mode..."
    if [ "$ENV" == "prod" ]; then
        bash "$DEPLOY_SCRIPT" "$MODE" "true"
    else
        ENV=$ENV python3 src/main.py --$MODE
    fi

    # 4. Archive
    log "📦 Archiving processed files to processed directory..."
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline/data/raw/staging/$F" "s3://trading-pipeline/data/raw/processed/$F"
    done
    log "✅ Batch #$BATCH_NUM complete. Files archived."

    MODE="daily"
    BATCH_NUM=$((BATCH_NUM + 1))
done