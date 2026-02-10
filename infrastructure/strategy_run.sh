#!/bin/bash
# strategy_run.sh - Run active strategies on EMR

# 1. Resolve Paths (Find Project Root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Check if we are running from the root or infrastructure and adjust
if [ -d "$PROJECT_ROOT/src" ]; then
    BASE_DIR="$PROJECT_ROOT"
else
    BASE_DIR="."
fi

echo "🏠 Project Root identified as: $BASE_DIR"

# 2. Package artifacts
echo "📦 Packaging project..."
mkdir -p "$BASE_DIR/dist"
# Zip from the root so internal paths in src.zip are correct
(cd "$BASE_DIR" && zip -rq dist/src.zip src strategies config filters -x "*.pyc" "__pycache__/*")

# 3. Sync to S3
S3_BUCKET="trading-pipeline"
echo "⬆️ Syncing artifacts to s3://$S3_BUCKET/artifacts/ ..."

aws s3 cp "$BASE_DIR/dist/src.zip" "s3://${S3_BUCKET}/artifacts/"
aws s3 cp "$BASE_DIR/config.yaml" "s3://${S3_BUCKET}/artifacts/"
aws s3 cp "$BASE_DIR/src/main.py" "s3://${S3_BUCKET}/artifacts/"

# 4. Trigger Remote Execution
# Ensure .application-id exists in the project root
if [ ! -f "$BASE_DIR/.application-id" ]; then
    echo "❌ Error: .application-id not found in $BASE_DIR"
    exit 1
fi

APP_ID=$(cat "$BASE_DIR/.application-id")
ROLE_ARN="arn:aws:iam::949934295366:role/EMRServerlessRole"

echo "🚀 Triggering EMR Strategy Orchestration for App: $APP_ID"

aws emr-serverless start-job-run \
  --application-id "$APP_ID" \
  --execution-role-arn "$ROLE_ARN" \
  --job-driver "{
    \"sparkSubmit\": {
        \"entryPoint\": \"s3://${S3_BUCKET}/artifacts/main.py\",
        \"entryPointArguments\": [\"--mode\", \"strategy\"],
        \"sparkSubmitParameters\": \"--py-files s3://${S3_BUCKET}/artifacts/src.zip\"
    }
  }"