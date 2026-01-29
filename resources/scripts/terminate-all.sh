#!/bin/bash

################################################################################
# Terminate All Trading Pipeline Resources
# Stops/Deletes EMR Serverless App, IAM Role, and Local Files
################################################################################

set -e

# Configuration
APP_NAME="TradingPipeline-Quick"
ROLE_NAME="EMRServerlessRole"
AWS_REGION="us-east-1"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting complete teardown of ${APP_NAME}...${NC}"

# 1. DELETE EMR SERVERLESS APPLICATION
# Find the Application ID by name if the local file is missing
APP_ID=$(aws emr-serverless list-applications \
  --region ${AWS_REGION} \
  --query "applications[?name=='${APP_NAME}' && state!='TERMINATED'].id" \
  --output text)

if [ ! -z "$APP_ID" ]; then
    echo -e "${GREEN}Stopping application: ${APP_ID}${NC}"
    # Application must be stopped before it can be deleted
    aws emr-serverless stop-application \
      --region ${AWS_REGION} \
      --application-id ${APP_ID} || echo "Application already stopping/stopped."

    echo "Waiting for application to transition to STOPPED state..."
    aws emr-serverless wait application-stopped \
      --region ${AWS_REGION} \
      --application-id ${APP_ID}

    echo -e "${GREEN}Deleting application: ${APP_ID}${NC}"
    aws emr-serverless delete-application \
      --region ${AWS_REGION} \
      --application-id ${APP_ID}

    rm -f .application-id
    echo -e "${GREEN}✓ EMR Application removed.${NC}"
else
    echo -e "${YELLOW}No active EMR Application found with name ${APP_NAME}.${NC}"
fi

# 2. DELETE IAM ROLE AND POLICIES
echo -e "${GREEN}Removing IAM Role and Permissions...${NC}"
# Delete the inline policy first
aws iam delete-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name EMRServerlessPermissions || echo "Policy not found."

# Delete the role
aws iam delete-role \
  --role-name ${ROLE_NAME} || echo "Role not found."
echo -e "${GREEN}✓ IAM resources removed.${NC}"

# 3. CLEAN LOCAL FILES
echo -e "${GREEN}Cleaning local workspace...${NC}"
rm -rf ./dist/
rm -f .job-run-id
rm -f .application-id
rm -f src.zip
rm -f pyspark_deps.tar.gz

echo -e "${GREEN}✓ COMPLETE: All compute and security resources have been terminated.${NC}"
echo -e "${YELLOW}Note: S3 data in 's3://trading-pipeline/' was kept. Delete manually if needed.${NC}"