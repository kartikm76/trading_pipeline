#!/bin/bash
# infrastructure/2_deploy_and_submit.sh - The Logic Translator

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"

source "$SCRIPT_DIR/env_discovery.sh"

# ── Step 1: Package & Upload Source Code to S3 ──
echo "📦 Packaging source code..."
DIST_DIR="$SCRIPT_DIR/dist"
mkdir -p "$DIST_DIR"
(cd "$PROJECT_ROOT/src" && zip -qr "$DIST_DIR/src.zip" . \
  -x '__pycache__/*' '*/__pycache__/*' '.DS_Store' 'codebase_snapshot.txt')

echo "☁️  Uploading artifacts to S3..."
aws s3 cp "$DIST_DIR/src.zip" s3://trading-pipeline/artifacts/src.zip --quiet
aws s3 cp "$PROJECT_ROOT/src/main.py" s3://trading-pipeline/artifacts/main.py --quiet
aws s3 cp "$PROJECT_ROOT/config.yaml" s3://trading-pipeline/artifacts/config.yaml --quiet
echo "✅ Artifacts uploaded"

# Accepts: bootstrap, daily, or strategy
RUN_TYPE=${1:-strategy}
get_val() { python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))$1)"; }

# MAP RUN_TYPE TO PROPERLY QUOTED JSON ARGUMENTS
if [ "$RUN_TYPE" == "bootstrap" ]; then
    PY_ARGS="\"--mode\", \"dataload\", \"--bootstrap\""
    SCALING_KEY="bootstrap"
elif [ "$RUN_TYPE" == "daily" ]; then
    PY_ARGS="\"--mode\", \"dataload\""
    SCALING_KEY="daily"
else
    # Default to Strategy SIT
    PY_ARGS="\"--mode\", \"strategy\""
    SCALING_KEY="daily"
fi

# Load Scaling and Spark Config
export MAX_EXECS=$(get_val "['scaling']['$SCALING_KEY']['max_executors']")
export EXEC_MEM=$(get_val "['scaling']['$SCALING_KEY']['executor_memory']")
export DRIV_MEM=$(get_val "['scaling']['$SCALING_KEY']['driver_memory']")
source "$(dirname "$0")/.spark_config"

echo "🚀 Submitting Job: Mode=[$RUN_TYPE] | Scaling=[$SCALING_KEY]"

aws emr-serverless start-job-run \
  --application-id "$APP_ID" \
  --execution-role-arn "$ROLE_ARN" \
  --job-driver "{
    \"sparkSubmit\": {
        \"entryPoint\": \"s3://trading-pipeline/artifacts/main.py\",
        \"entryPointArguments\": [$PY_ARGS],
        \"sparkSubmitParameters\": \"$SUBMIT_PARAMS\"
    }
  }"