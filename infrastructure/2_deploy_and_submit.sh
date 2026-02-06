#!/bin/bash
set -e

MODE=$1
SKIP_UPLOAD=${2:-"false"}
CONFIG_FILE="config.yaml"

# Timestamp function for logging
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $1"; }

# 1. --- DYNAMIC INFRASTRUCTURE PARAMS ---
get_val() { python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))$1)"; }

# Determine which scaling block to use (default to bootstrap if deploy-only)
SCALING_MODE=$MODE
if [ "$MODE" == "deploy-only" ]; then
    SCALING_MODE="bootstrap"
fi

S3_BUCKET=$(get_val "['prod']['warehouse']" | cut -d'/' -f3)
APP_ID=$(cat .application-id)
ROLE_ARN="arn:aws:iam::949934295366:role/EMRServerlessRole"
MAX_EXECS=$(get_val "['scaling']['$SCALING_MODE']['max_executors']")
EXEC_MEM=$(get_val "['scaling']['$SCALING_MODE']['executor_memory']")
DRIV_MEM=$(get_val "['scaling']['$SCALING_MODE']['driver_memory']")
IS_BOOTSTRAP=$([ "$MODE" == "bootstrap" ] && echo "true" || echo "false")

# 🚨 Export variables so infrastructure/.spark_config can resolve them
export MAX_EXECS EXEC_MEM DRIV_MEM IS_BOOTSTRAP S3_BUCKET

# 2. --- SOURCE THE SPARK CONFIG ---
if [ -f "infrastructure/.spark_config" ]; then
    source infrastructure/.spark_config
else
    log "❌ Error: infrastructure/.spark_config not found."
    exit 1
fi

# 3. --- DEPLOYMENT PHASE ---
if [ "$MODE" == "deploy-only" ] || [ "$SKIP_UPLOAD" == "false" ]; then
    log "📂 Phase 1: Deploying artifacts to S3..."
    mkdir -p dist
    # Package source code
    log "📦 Packaging source code..."
    (cd src && zip -r ../dist/src.zip . -x "*.pyc" "__pycache__/*")

    # Upload to S3
    log "⬆️  Uploading artifacts to S3..."
    aws s3 cp dist/src.zip s3://${S3_BUCKET}/artifacts/
    aws s3 cp config.yaml s3://${S3_BUCKET}/artifacts/
    aws s3 cp src/main.py s3://${S3_BUCKET}/artifacts/

    # Exit early if we only wanted to deploy
    if [ "$MODE" == "deploy-only" ]; then
        log "✅ Artifacts Deployed."
        exit 0
    fi
fi

# 4. --- SUBMISSION PHASE ---
# Map bash MODE to the Python CLI flag expected by main.py
if [ "$MODE" == "bootstrap" ]; then
    PY_FLAG="--bootstrap"
else
    PY_FLAG="--daily"
fi

log "🔍 DEBUG: Mode is [$MODE]. Passing flag [$PY_FLAG] to Python."
log "🔍 DEBUG: SUBMIT_PARAMS are: $SUBMIT_PARAMS"

# 🚨 FIXED: Now using entryPointArguments to pass the flag to sys.argv
JOB_DRIVER=$(printf '{
    "sparkSubmit": {
        "entryPoint": "s3://%s/artifacts/main.py",
        "entryPointArguments": ["%s"],
        "sparkSubmitParameters": "%s"
    }
}' "$S3_BUCKET" "$PY_FLAG" "$SUBMIT_PARAMS")

log "🚀 Submitting $MODE job to EMR Serverless..."
JOB_RUN_ID=$(aws emr-serverless start-job-run \
  --application-id "$APP_ID" \
  --execution-role-arn "$ROLE_ARN" \
  --job-driver "$JOB_DRIVER" \
  --query 'jobRunId' --output text)

# 5. --- POLLING LOOP ---
log "⏳ Monitoring Job: $JOB_RUN_ID"
while true; do
    STATE=$(aws emr-serverless get-job-run --application-id "$APP_ID" --job-run-id "$JOB_RUN_ID" --query 'jobRun.state' --output text)
    if [ "$STATE" == "SUCCESS" ]; then
        log "✅ Batch Success."
        break
    elif [[ "$STATE" == "FAILED" || "$STATE" == "CANCELLED" ]]; then
        log "❌ Job $STATE. Check EMR Serverless logs for details."
        exit 1
    fi
    sleep 30
done