#!/bin/bash

################################################################################
# Trading Pipeline - EMR Serverless Deployment Script
# This script packages and deploys the trading pipeline to AWS EMR Serverless
################################################################################

set -e  # Exit on error

# Configuration
PROJECT_NAME="trading-pipeline"
S3_BUCKET="s3://trading-pipeline"
S3_CODE_PATH="${S3_BUCKET}/code"
S3_SCRIPTS_PATH="${S3_BUCKET}/scripts"
AWS_REGION="us-east-1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured. Run 'aws configure' first."
    exit 1
fi

log_info "Starting deployment for ${PROJECT_NAME}..."

# Step 1: Clean previous builds
log_info "Cleaning previous builds..."
rm -f trading_pipeline.zip
rm -rf build/

# Step 2: Create package
log_info "Creating deployment package..."
mkdir -p build
cp main.py build/
cp -r src/ build/
cp -r resources/ build/
cp requirements.txt build/

# Create zip file
cd build
zip -r ../trading_pipeline.zip . -x "*.pyc" -x "__pycache__/*" -x "*.git/*" -x "*.DS_Store"
cd ..

log_info "Package created: trading_pipeline.zip ($(du -h trading_pipeline.zip | cut -f1))"

# Step 3: Upload to S3
log_info "Uploading code to S3..."
aws s3 cp trading_pipeline.zip ${S3_CODE_PATH}/trading_pipeline.zip
aws s3 cp requirements.txt ${S3_CODE_PATH}/requirements.txt
aws s3 cp main.py ${S3_CODE_PATH}/main.py

log_info "${GREEN}✓ Deployment complete!${NC}"
log_info "Code uploaded to: ${S3_CODE_PATH}"
log_info ""
log_info "Next steps:"
log_info "  1. Create EMR Serverless application (one-time): ./resources/scripts/2-create-application.sh"
log_info "  2. Submit job: ./resources/scripts/4-submit-job.sh"

# Cleanup
rm -rf build/