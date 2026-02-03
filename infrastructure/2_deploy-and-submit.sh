#!/bin/bash
set -e

# --- 1. CAPTURE ARGUMENT ---
MODE=${1:-daily}
IS_BOOTSTRAP="false"
MAX_EXECUTORS=20
EXEC_MEM="8G"
DRIV_MEM="8G"

# --- 1. CAPTURE ARGUMENT ---
if [ "$MODE" == "bootstrap" ]; then
    echo "🚨 BOOTSTRAP MODE DETECTED: Scaling up for 200GB load..."
    IS_BOOTSTRAP="true"
    MAX_EXECUTORS=100
    EXEC_MEM="16G"
    DRIV_MEM="32G" # Increased for 200GB metadata handling
fi

# --- 2. CONFIGURATION ---
S3_BUCKET="trading-pipeline"
AWS_REGION="us-east-1"
DIST_DIR="./dist"
mkdir -p $DIST_DIR

# --- 3. SOURCE PARAMS (After variables are defined) ---
## This ensures ${S3_BUCKET} and ${IS_BOOTSTRAP} are expanded correctly
source infrastructure/.spark_conf

# --- 4. PACKAGING ---
# Rebuilding the zip to support 'import adapters' (Flat structure)
echo "📂 Packaging source code (Flat structure for Hatch compatibility)..."
(cd src && zip -r ../$DIST_DIR/src.zip . -x "*.pyc" "__pycache__/*")

aws s3 cp $DIST_DIR/src.zip s3://$S3_BUCKET/artifacts/
aws s3 cp config.yaml s3://$S3_BUCKET/artifacts/
aws s3 cp src/main.py s3://$S3_BUCKET/artifacts/

# --- 5. EMR SERVERLESS SUBMISSION ---
APP_ID=$(cat .application-id)
# 🚨 ENSURE YOU UPDATE YOUR ACCOUNT ID HERE
EXECUTION_ROLE_ARN="arn:aws:iam::949934295366:role/EMRServerlessRole"

echo "Submitting $MODE job to Application $APP_ID..."

# Clean the params: remove potential newlines and extra spaces
CLEAN_PARAMS=$(echo $SUBMIT_PARAMS | tr -d '\n' | tr -s ' ')

# Build the JSON block using a variable to avoid quote nesting issues
JOB_DRIVER=$(printf '{
    "sparkSubmit": {
        "entryPoint": "s3://%s/artifacts/main.py",
        "sparkSubmitParameters": "%s"
    }
}' "$S3_BUCKET" "$CLEAN_PARAMS")

JOB_RUN_ID=$(aws emr-serverless start-job-run \
  --region ${AWS_REGION} \
  --application-id ${APP_ID} \
  --execution-role-arn ${EXECUTION_ROLE_ARN} \
  --job-driver "$JOB_DRIVER" \
  --query 'jobRunId' --output text)

echo "✅ Job submitted: $JOB_RUN_ID"