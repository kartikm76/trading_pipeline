#!/bin/bash

################################################################################
# Create EMR Serverless Application
# This is a one-time setup - creates the EMR Serverless application
################################################################################

set -e

# Configuration
APP_NAME="TradingPipeline"
RELEASE_LABEL="emr-7.1.0"
APP_TYPE="SPARK"
S3_BUCKET="s3://trading-pipeline"
AWS_REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Creating EMR Serverless application: ${APP_NAME}${NC}"

# Check if application already exists
EXISTING_APP=$(aws emr-serverless list-applications \
  --region ${AWS_REGION} \
  --query "applications[?name=='${APP_NAME}'].id" \
  --output text)

if [ ! -z "$EXISTING_APP" ]; then
    echo -e "${YELLOW}Application already exists: ${EXISTING_APP}${NC}"
    echo ${EXISTING_APP} > .application-id
    echo "Saved to .application-id"
    exit 0
fi

# Create application
APP_ID=$(aws emr-serverless create-application \
  --region ${AWS_REGION} \
  --name ${APP_NAME} \
  --release-label ${RELEASE_LABEL} \
  --type ${APP_TYPE} \
  --initial-capacity '{
    "DRIVER": {
      "workerCount": 1,
      "workerConfiguration": {
        "cpu": "2vCPU",
        "memory": "4GB",
        "disk": "20GB"
      }
    },
    "EXECUTOR": {
      "workerCount": 2,
      "workerConfiguration": {
        "cpu": "4vCPU",
        "memory": "8GB",
        "disk": "20GB"
      }
    }
  }' \
  --maximum-capacity '{
    "cpu": "20vCPU",
    "memory": "40GB",
    "disk": "100GB"
  }' \
  --auto-start-configuration '{
    "enabled": true
  }' \
  --auto-stop-configuration '{
    "enabled": true,
    "idleTimeoutMinutes": 15
  }' \
  --network-configuration '{
    "subnetIds": [],
    "securityGroupIds": []
  }' \
  --query 'applicationId' \
  --output text)

echo -e "${GREEN}✓ Application created: ${APP_ID}${NC}"
echo ""
echo "Application is starting up. This may take 1-2 minutes."
echo ""
echo "Monitor status:"
echo "  aws emr-serverless get-application --application-id ${APP_ID} --query 'application.state'"
echo ""
echo "Once application is CREATED, submit job:"
echo "  ./scripts/submit-job.sh"
echo ""
echo "Save this application ID: ${APP_ID}"

# Save application ID to file
echo ${APP_ID} > .application-id

echo ""
echo -e "${YELLOW}Note: This is a one-time setup. You can reuse this application for all future jobs.${NC}"