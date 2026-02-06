#!/bin/bash

export ENV=${1:-dev}
CONFIG="config.yaml"

echo "🏁 Starting Batch Controller [Env: $ENV]"

# Python helper to read from the DRY config
get_val() { python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))$1)"; }

BASE=$(get_val "['$ENV']['raw_base_path']")
BATCH_SIZE=$(get_val "['scaling']['batch_size']")

[[ "${BASE}" != */ ]] && BASE="${BASE}/"

LANDING="${BASE}landing/"
STAGING="${BASE}staging/"
PROCESSED="${BASE}processed/"

MODE="bootstrap"

while true; do
    # List batch
    if [[ $BASE == s3://* ]]; then
        FILES=$(aws s3 ls "$LANDING" | grep ".csv" | awk '{print $4}' | head -n $BATCH_SIZE)
        MV_CMD="aws s3 mv"
    else
        FILES=$(ls -1 "$LANDING" 2>/dev/null | grep ".csv" | head -n $BATCH_SIZE)
        MV_CMD="mv"
    fi

    if [ -z "$FILES" ]; then
        echo "✅ All files processed."
        break
    fi

    # Linear Move: Landing -> Staging
    for F in $FILES; do
        $MV_CMD "$LANDING$F" "$STAGING$F"
    done

    # Run Spark Logic
    if [ "$ENV" == "prod" ]; then
        ./infrastructure/2_deploy_and_submit.sh "$MODE"
    else
        ENV=$ENV python3 src/main.py --$MODE
    fi

    # Linear Move: Staging -> Processed
    if [ $? -eq 0 ]; then
        for F in $FILES; do
            $MV_CMD "$STAGING$F" "$PROCESSED$F"
        done
        MODE="daily"
    else
        echo "❌ Job failed. Files preserved in $STAGING"
        exit 1
    fi
done