#!/bin/bash

################################################################################
# Watch EMR Serverless Job Progress
# Monitors the status of a running EMR Serverless job
################################################################################

set -e

JOB_RUN_ID=$1
AWS_REGION="us-east-1"

if [ -z "$JOB_RUN_ID" ]; then
    if [ -f .job-run-id ]; then
        JOB_RUN_ID=$(cat .job-run-id)
        echo "Using job run ID from .job-run-id: ${JOB_RUN_ID}"
    else
        echo "Usage: $0 <job-run-id>"
        exit 1
    fi
fi

if [ ! -f .application-id ]; then
    echo "Error: No application ID found"
    exit 1
fi

APP_ID=$(cat .application-id)

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Watching job progress..."
echo "Press Ctrl+C to stop watching (job will continue running)"
echo ""

while true; do
    RESPONSE=$(aws emr-serverless get-job-run \
      --region ${AWS_REGION} \
      --application-id ${APP_ID} \
      --job-run-id ${JOB_RUN_ID} \
      --query 'jobRun.{state:state,stateDetails:stateDetails}' \
      --output json)

    STATUS=$(echo $RESPONSE | jq -r '.state')
    DETAILS=$(echo $RESPONSE | jq -r '.stateDetails')

    case $STATUS in
        PENDING|SCHEDULED|SUBMITTED)
            echo -e "${YELLOW}Status: ${STATUS}${NC}"
            ;;
        RUNNING)
            echo -e "${YELLOW}Status: RUNNING - ${DETAILS}${NC}"
            ;;
        SUCCESS)
            echo -e "${GREEN}✓ Status: SUCCESS${NC}"
            exit 0
            ;;
        FAILED)
            echo -e "${RED}✗ Status: FAILED - ${DETAILS}${NC}"
            echo "Check logs for details:"
            echo "  aws s3 ls s3://trading-pipeline/logs/applications/${APP_ID}/jobs/${JOB_RUN_ID}/"
            exit 1
            ;;
        CANCELLING|CANCELLED)
            echo -e "${RED}✗ Status: ${STATUS}${NC}"
            exit 1
            ;;
    esac

    sleep 10
done