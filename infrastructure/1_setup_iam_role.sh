#!/bin/bash

################################################################################
# Setup IAM Role for EMR Serverless
# Creates the necessary IAM role with permissions
################################################################################

set -e

ROLE_NAME="EMRServerlessRole"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Creating IAM role: ${ROLE_NAME}${NC}"

# Create trust policy
cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ops.emr-serverless.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name ${ROLE_NAME} \
  --assume-role-policy-document file:///tmp/trust-policy.json || echo "Role may already exist"

# Create permissions policy
cat > /tmp/permissions-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:AbortMultipartUpload"
      ],
      "Resource": [
        "arn:aws:s3:::trading-pipeline/*",
        "arn:aws:s3:::trading-pipeline"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:CreateDatabase",
        "glue:GetTable",
        "glue:CreateTable",
        "glue:UpdateTable",
        "glue:DeleteTable",
        "glue:GetTables",
        "glue:BatchCreatePartition",
        "glue:BatchDeletePartition",
        "glue:GetPartition",
        "glue:GetPartitions"
      ],
      "Resource": [
        "arn:aws:glue:us-east-1:${AWS_ACCOUNT_ID}:catalog",
        "arn:aws:glue:us-east-1:${AWS_ACCOUNT_ID}:database/trading_db",
        "arn:aws:glue:us-east-1:${AWS_ACCOUNT_ID}:table/trading_db/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF

# Attach policy
aws iam put-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name EMRServerlessPermissions \
  --policy-document file:///tmp/permissions-policy.json

echo -e "${GREEN}✓ IAM role created: arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}${NC}"
echo ""
echo "Update this ARN in scripts/submit-job.sh:"
echo "  EXECUTION_ROLE_ARN=\"arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}\""

# Cleanup
rm /tmp/trust-policy.json /tmp/permissions-policy.json