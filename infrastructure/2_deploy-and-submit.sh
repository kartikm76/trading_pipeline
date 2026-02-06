#!/bin/bash
set -e

MODE=${1:-daily}
CONFIG="config.yaml"

# Programmatic extraction using Python
get_val() { python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))$1)"; }

# Fetch EMR/Spark params
MAX_EXECS=$(get_val "['scaling']['$MODE']['max_executors']")
EXEC_MEM=$(get_val "['scaling']['$MODE']['executor_memory']")
DRIV_MEM=$(get_val "['scaling']['$MODE']['driver_memory']")
S3_BUCKET=$(get_val "['prod']['warehouse']" | cut -d'/' -f3)

# App ID from local file
APP_ID=$(cat .application-id)
ROLE_ARN="arn:aws:iam::949934295366:role/EMRServerlessRole"

BOOTSTRAP_ARG=""
if [ "$MODE" == "bootstrap" ]; then BOOTSTRAP_ARG="--bootstrap"; fi

# Packaging
echo "📂 Packaging source code..."
(cd src && zip -r ../dist/src.zip . -x "*.pyc" "__pycache__/*")
aws s3 cp dist/src.zip s3://$S3_BUCKET/artifacts/
aws s3 cp config.yaml s3://$S3_BUCKET/artifacts/
aws s3 cp src/main.py s3://$S3_BUCKET/artifacts/

# Build Submit Params
SPARK_PARAMS="--conf spark.executor.instances=$MAX_EXECS
--conf spark.executor.memory=$EXEC_MEM
--conf spark.driver.memory=$DRIV_MEM
--conf spark.submit.pyFiles=s3://$S3_BUCKET/artifacts/src.zip"

JOB_DRIVER=$(printf '{
    "sparkSubmit": {
        "entryPoint": "s3://%s/artifacts/main.py",
        "entryPointArguments": ["%s"],
        "sparkSubmitParameters": "%s"
    }
}' "$S3_BUCKET" "$BOOTSTRAP_ARG" "$SPARK_PARAMS")

echo "🚀 Submitting $MODE job to EMR Serverless..."
JOB_RUN_ID=$(aws emr-serverless start-job-run \
  --application-id $APP_ID \
  --execution-role-arn $ROLE_ARN \
  --job-driver "$JOB_DRIVER" \
  --query 'jobRunId' \
  --output text)

aws emr-serverless wait job-run-completed --application-id $APP_ID --job-run-id $JOB_RUN_ID