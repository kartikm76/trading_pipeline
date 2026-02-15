#!/bin/bash
# 0_batch_pipeline.sh - Master Production Orchestrator

# 1. Update Infrastructure (Ensures AWS Image == Local Code)
./infrastructure/build_image.sh

# 2. Setup Loop
MODE="bootstrap"
while true; do
    echo "📋 Checking for data batch in landing zone..."
    FILES=$(aws s3 ls s3://trading-pipeline/data/raw/landing/ | grep ".csv" | awk '{print $4}' | head -n 15)

    if [ -z "$FILES" ]; then
        echo "✅ No more files to process. Pipeline complete."
        break
    fi

    # Phase 1: Landing -> Staging
    echo "📁 Moving batch to staging..."
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline/data/raw/landing/$F" "s3://trading-pipeline/data/raw/staging/$F"
    done

    # Phase 2: Execution (Calls the Internal Worker)
    echo "🚀 Submitting Spark Job ($MODE mode)..."
    ./infrastructure/deploy_and_submit.sh "$MODE"

    # Phase 3: Archive (Staging -> Processed)
    echo "📦 Archiving processed batch..."
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline/data/raw/staging/$F" "s3://trading-pipeline/data/raw/processed/$F"
    done

    # Switch to incremental after the first successful bootstrap batch
    MODE="daily"
done