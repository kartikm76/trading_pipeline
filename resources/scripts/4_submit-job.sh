#!/bin/bash

################################################################################
# Submit Spark Job to EMR Serverless
# Submits the trading pipeline job to EMR Serverless
################################################################################

set -e

# Configuration
S3_BUCKET="s3://trading-pipeline"
S3_CODE_PATH="${S3_BUCKET}/code"
S3_LOGS_PATH="${S3_BUCKET}/logs"
AWS_REGION="us-east-1"
EXECUTION_ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT_ID:role/EMRServerlessRole"  # Update this!

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get application ID
if [ -f .application-id ]; then
    APP_ID=$(cat .application-id)
    echo -e "${YELLOW}Using application ID from .application-id: ${APP_ID}${NC}"
else
    echo -e "${RED}Error: No application ID found${NC}"
    echo "Run ./scripts/create-application.sh first"
    exit 1
fi

# Check application status
echo "Checking application status..."
APP_STATE=$(aws emr-serverless get-application \
  --region ${AWS_REGION} \
  --application-id ${APP_ID} \
  --query 'application.state' \
  --output text)

if [ "$APP_STATE" != "CREATED" ]; then
    echo -e "${YELLOW}Application is in ${APP_STATE} state. Waiting for CREATED state...${NC}"

    # Wait for application to be ready
    aws emr-serverless get-application \
      --region ${AWS_REGION} \
      --application-id ${APP_ID} \
      --query 'application.state' \
      --output text | grep -q "CREATED" || {
        echo -e "${RED}Application not ready. Current state: ${APP_STATE}${NC}"
        exit 1
      }
fi

echo -e "${GREEN}Application is ready. Submitting job...${NC}"

# Submit job
JOB_RUN_ID=$(aws emr-serverless start-job-run \
  --region ${AWS_REGION} \
  --application-id ${APP_ID} \
  --execution-role-arn ${EXECUTION_ROLE_ARN} \
  --job-driver '{
    "sparkSubmit": {
      "entryPoint": "'"${S3_CODE_PATH}/main.py"'",
      "entryPointArguments": [],
      "sparkSubmitParameters": "--conf spark.executor.cores=4 --conf spark.executor.memory=8g --conf spark.driver.cores=2 --conf spark.driver.memory=4g --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog --conf spark.sql.catalog.glue_catalog.warehouse='"${S3_BUCKET}/iceberg-warehouse/"' --conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO --conf spark.jars=/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar --conf spark.archives='"${S3_CODE_PATH}/trading_pipeline.zip#pyfiles"' --py-files pyfiles/trading_pipeline.zip"
    }
  }' \
  --configuration-overrides '{
    "monitoringConfiguration": {
      "s3MonitoringConfiguration": {
        "logUri": "'"${S3_LOGS_PATH}/"'"
      }
    }
  }' \
  --query 'jobRunId' \
  --output text)

echo -e "${GREEN}✓ Job submitted: ${JOB_RUN_ID}${NC}"
echo ""
echo "Monitor job status:"
echo "  aws emr-serverless get-job-run --application-id ${APP_ID} --job-run-id ${JOB_RUN_ID} --query 'jobRun.state'"
echo ""
echo "View logs:"
echo "  aws s3 ls ${S3_LOGS_PATH}/applications/${APP_ID}/jobs/${JOB_RUN_ID}/"
echo ""
echo "Watch job progress:"
echo "  ./scripts/watch-job.sh ${JOB_RUN_ID}"

# Save job run ID
echo ${JOB_RUN_ID} > .job-run-id