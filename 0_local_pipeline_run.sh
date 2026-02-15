#!/bin/bash
# 0_local_pipeline_run.sh - Local Dev Orchestrator
#
# Local equivalent of 0_aws_pipeline_run.sh (which is AWS-only).
# Moves CSVs through landing → staging → processed on the local filesystem
# and runs the Spark dataload pipeline locally via PySpark.
#
# Usage:
#   ./0_local_pipeline_run.sh              # Process all CSVs from landing/
#   ./0_local_pipeline_run.sh --batch 5    # Process 5 files at a time

set -euo pipefail

LANDING_DIR="./data/raw/landing"
STAGING_DIR="./data/raw/staging"
PROCESSED_DIR="./data/raw/processed"
BATCH_SIZE=15

# Parse optional --batch flag
while [[ $# -gt 0 ]]; do
    case $1 in
        --batch) BATCH_SIZE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Ensure directories exist
mkdir -p "$LANDING_DIR" "$STAGING_DIR" "$PROCESSED_DIR"

MODE="bootstrap"
while true; do
    echo "📋 Checking for CSVs in landing zone..."
    FILES=$(find "$LANDING_DIR" -maxdepth 1 -name "*.csv" -type f | head -n "$BATCH_SIZE")

    if [ -z "$FILES" ]; then
        echo "✅ No more files to process. Pipeline complete."
        break
    fi

    FILE_COUNT=$(echo "$FILES" | wc -l | tr -d ' ')
    echo "📁 Moving $FILE_COUNT file(s) to staging..."

    # Phase 1: Landing → Staging
    for F in $FILES; do
        mv "$F" "$STAGING_DIR/"
    done

    # Phase 2: Run Spark dataload locally
    echo "🚀 Running Spark dataload ($MODE mode)..."
    if [ "$MODE" == "bootstrap" ]; then
        ENV=dev uv run python src/main.py --mode dataload --bootstrap
    else
        ENV=dev uv run python src/main.py --mode dataload
    fi

    # Phase 3: Staging → Processed
    echo "📦 Archiving processed files..."
    for F in "$STAGING_DIR"/*.csv; do
        [ -f "$F" ] && mv "$F" "$PROCESSED_DIR/"
    done

    # Switch to incremental after first bootstrap
    MODE="daily"
done

echo "🏁 Local batch pipeline finished."
