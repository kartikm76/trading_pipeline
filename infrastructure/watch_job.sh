#!/bin/bash
# watch_job.sh - Monitor EMR Job Progress

source infrastructure/env_discovery.sh

JOB_RUN_ID=$1
if [ -z "$JOB_RUN_ID" ] && [ -f .job-run-id ]; then
    JOB_RUN_ID=$(cat .job-run-id)
fi

[ -z "$JOB_RUN_ID" ] && { echo "Usage: $0 <job-run-id>"; exit 1; }

echo "Watching job: $JOB_RUN_ID on App: $APP_ID..."

while true; do
    RESPONSE=$(aws emr-serverless get-job-run \
      --region ${AWS_REGION} \
      --application-id ${APP_ID} \
      --job-run-id ${JOB_RUN_ID} \
      --query 'jobRun.{state:state,details:stateDetails}' --output json)

    STATUS=$(echo $RESPONSE | jq -r '.state')

    case $STATUS in
        RUNNING) echo "Status: RUNNING";;
        SUCCESS) echo "✓ Status: SUCCESS"; exit 0;;
        FAILED)  echo "✗ Status: FAILED"; exit 1;;
        *)       echo "Status: $STATUS";;
    esac
    sleep 10
done