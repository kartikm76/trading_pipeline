#!/bin/bash
set -e
source $(dirname "$0")/.spark_conf

# --- 1. SET PROJECT ROOT ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$PROJECT_ROOT"

# --- CONFIGURATION ---
S3_BUCKET="trading-pipeline"
EXECUTION_ROLE_ARN="arn:aws:iam::949934295366:role/EMRServerlessRole"
REGION="us-east-1"
APP_NAME="TradingPipeline-Quick"
DIST_DIR="./dist"

# Create dist directory if it doesn't exist
mkdir -p $DIST_DIR

# --- 2. CONDITIONAL DEPENDENCY PACKAGING (The Slow Part) ---
# We only run Docker if the tar.gz doesn't exist or requirements.txt is newer
if [ ! -f "$DIST_DIR/pyspark_deps.tar.gz" ] || [ "requirements.txt" -nt "$DIST_DIR/pyspark_deps.tar.gz" ]; then
    echo "📦 Requirements changed or missing. Rebuilding dependencies with Docker (Slow)..."
    docker run --rm -v $(pwd):/app -w /app --platform linux/amd64 amazonlinux:2023 /bin/bash -c "
      yum install -y python3 tar gzip zip
      python3 -m venv venv_emr
      source venv_emr/bin/activate
      pip install --upgrade pip
      pip install -r requirements.txt venv-pack
      venv-pack -o /app/dist/pyspark_deps.tar.gz
      rm -rf venv_emr
    "
else
    echo "✅ Dependencies unchanged. Skipping Docker build (Fast)."
fi

# --- 3. PACKAGE SOURCE CODE (The Fast Part) ---
echo "⚡ Zipping source code and config..."

# Hard-reset the dist directory variable to be safe
DIST_DIR="./dist"
mkdir -p "$DIST_DIR"

# Explicitly remove the old zip to prevent "identity" errors
rm -f "$DIST_DIR/src.zip"

# Re-run the zip from the project root
# We use quotes around the path to prevent expansion errors
zip -r "$DIST_DIR/src.zip" src/

# Copy the entry point and config
cp main.py "$DIST_DIR/"
cp config.yaml "$DIST_DIR/"

echo "✅ Code packaged in $DIST_DIR"

# --- 4. UPLOAD TO S3 ---
echo "🚀 Uploading updated artifacts to S3..."
aws s3 sync $DIST_DIR/ s3://${S3_BUCKET}/artifacts/ --delete

# --- 5. ENSURE EMR APP EXISTS ---
APP_ID=$(aws emr-serverless list-applications --query "applications[?name=='${APP_NAME}' && state=='CREATED'].id" --output text)

if [ -z "$APP_ID" ]; then
    echo "Creating new EMR Application..."
    APP_ID=$(aws emr-serverless create-application \
      --type "SPARK" \
      --name "$APP_NAME" \
      --release-label "emr-7.1.0" \
      --query "applicationId" --output text)
    sleep 10
fi

# --- 6. SUBMIT JOB ---
echo "🎯 Submitting Job to Application: $APP_ID"

aws emr-serverless start-job-run \
  --application-id "$APP_ID" \
  --execution-role-arn "$EXECUTION_ROLE_ARN" \
  --job-driver "{
    \"sparkSubmit\": {
      \"entryPoint\": \"s3://${S3_BUCKET}/artifacts/main.py\",
      \"sparkSubmitParameters\": \"'$SUBMIT_PARAMS'\"
    }
  }"

echo "Job Submitted Successfully!"