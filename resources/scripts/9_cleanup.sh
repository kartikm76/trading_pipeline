#!/bin/bash

################################################################################
# Cleanup EMR Serverless Resources
# Stops application and cleans up local files
################################################################################

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

AWS_REGION="us-east-1"

if [ -f .application-id ]; then
    APP_ID=$(cat .application-id)

    echo -e "${YELLOW}Do you want to delete the EMR Serverless application? (y/N)${NC}"
    read -r response

    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${GREEN}Stopping application: ${APP_ID}${NC}"
        aws emr-serverless stop-application \
          --region ${AWS_REGION} \
          --application-id ${APP_ID}

        echo "Waiting for application to stop..."
        sleep 10

        echo -e "${GREEN}Deleting application: ${APP_ID}${NC}"
        aws emr-serverless delete-application \
          --region ${AWS_REGION} \
          --application-id ${APP_ID}

        rm .application-id
        echo -e "${GREEN}✓ Application deleted${NC}"
    else
        echo -e "${YELLOW}Application kept. You can reuse it for future jobs.${NC}"
    fi
else
    echo -e "${RED}No application ID found${NC}"
fi

# Clean local files
echo "Cleaning local files..."
rm -f trading_pipeline.zip
rm -f .job-run-id
rm -rf build/

echo -e "${GREEN}✓ Cleanup complete${NC}"