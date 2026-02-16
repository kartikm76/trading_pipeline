#!/bin/bash
# 0_aws_pipeline_run_test.sh - AWS Test Environment Orchestrator
#
# Test environment for performance optimization testing.
# Uses s3://trading-pipeline-test/ bucket and trading_db_test Glue database.
#
# Usage:
#   ./0_aws_pipeline_run_test.sh              # Bootstrap: process ALL files in ONE job
#   ./0_aws_pipeline_run_test.sh --batch      # Daily: batch mode (15 files at a time)

set -euo pipefail

BATCH_MODE=false

# Parse optional --batch flag for daily incremental loads
if [[ "${1:-}" == "--batch" ]]; then
    BATCH_MODE=true
fi

# Bootstrap mode: process all files in ONE job (PERFORMANCE OPTIMIZATION TEST)
if [ "$BATCH_MODE" = false ]; then
    echo "📋 TEST Bootstrap mode: Moving ALL files from landing → staging..."
    FILES=$(aws s3 ls s3://trading-pipeline-test/data/raw/landing/ | grep ".csv" | awk '{print $4}')

    if [ -z "$FILES" ]; then
        echo "✅ No files to process."
        exit 0
    fi

    FILE_COUNT=$(echo "$FILES" | wc -l | tr -d ' ')
    echo "📁 Moving $FILE_COUNT file(s) to staging..."

    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline-test/data/raw/landing/$F" "s3://trading-pipeline-test/data/raw/staging/$F"
    done

    echo "🚀 Submitting ONE Spark job (bootstrap mode, $FILE_COUNT files)..."
    ENV=test ./infrastructure/deploy_and_submit.sh "bootstrap"

    echo "📦 Archiving $FILE_COUNT processed file(s)..."
    for F in $FILES; do
        aws s3 mv "s3://trading-pipeline-test/data/raw/staging/$F" "s3://trading-pipeline-test/data/raw/processed/$F"
    done

    echo "✅ TEST Bootstrap complete ($FILE_COUNT files processed in ONE job)."
else
    # Batch mode: process 15 files at a time (for daily incremental loads)
    MODE="daily"
    while true; do
        echo "📋 TEST: Checking for data batch in landing zone..."
        FILES=$(aws s3 ls s3://trading-pipeline-test/data/raw/landing/ | grep ".csv" | awk '{print $4}' | head -n 15)

        if [ -z "$FILES" ]; then
            echo "✅ No more files to process. Pipeline complete."
            break
        fi

        # Phase 1: Landing -> Staging
        echo "📁 Moving batch to staging..."
        for F in $FILES; do
            aws s3 mv "s3://trading-pipeline-test/data/raw/landing/$F" "s3://trading-pipeline-test/data/raw/staging/$F"
        done

        # Phase 2: Execution
        echo "🚀 Submitting Spark Job ($MODE mode)..."
        ENV=test ./infrastructure/deploy_and_submit.sh "$MODE"

        # Phase 3: Archive
        echo "📦 Archiving processed batch..."
        for F in $FILES; do
            aws s3 mv "s3://trading-pipeline-test/data/raw/staging/$F" "s3://trading-pipeline-test/data/raw/processed/$F"
        done
    done
fi
