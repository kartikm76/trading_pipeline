#!/bin/bash
# setup_iam_role.sh - The "Final Word" on Security

set -e
INFRA_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${INFRA_DIR}/env_discovery.sh"

ROLE_NAME="EMRServerlessRole"
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Applying Final Security Layer...${NC}"

# 1. Unified Trust Policy (Covers both possible Service Principals)
cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Service": ["emr-serverless.amazonaws.com", "ops.emr-serverless.amazonaws.com"]
    },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role --role-name ${ROLE_NAME} --assume-role-policy-document file:///tmp/trust-policy.json || \
aws iam update-assume-role-policy --role-name ${ROLE_NAME} --policy-document file:///tmp/trust-policy.json

# 2. Comprehensive Permissions Policy
cat > /tmp/permissions-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": ["arn:aws:s3:::trading-pipeline/*", "arn:aws:s3:::trading-pipeline"]
    },
    {
      "Effect": "Allow",
      "Action": ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartition", "glue:GetPartitions"],
      "Resource": ["arn:aws:glue:${AWS_REGION}:${AWS_ACCOUNT_ID}:catalog", "arn:aws:glue:${AWS_REGION}:${AWS_ACCOUNT_ID}:database/trading_db", "arn:aws:glue:${AWS_REGION}:${AWS_ACCOUNT_ID}:table/trading_db/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["ecr:GetAuthorizationToken"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["ecr:BatchGetImage", "ecr:DescribeImages", "ecr:GetDownloadUrlForLayer"],
      "Resource": "arn:aws:ecr:${AWS_REGION}:${AWS_ACCOUNT_ID}:repository/${REPO_NAME}"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogGroups", "logs:DescribeLogStreams"],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF

aws iam put-role-policy --role-name ${ROLE_NAME} --policy-name EMRServerlessPermissions --policy-document file:///tmp/permissions-policy.json

# 3. ECR Repository Resource Policy (The "Bouncer" Fix)
cat > /tmp/ecr-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowEMRServerlessFullAccess",
      "Effect": "Allow",
      "Principal": {
        "Service": ["emr-serverless.amazonaws.com", "ops.emr-serverless.amazonaws.com"]
      },
      "Action": [
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:GetDownloadUrlForLayer"
      ]
    }
  ]
}
EOF

aws ecr set-repository-policy --repository-name ${REPO_NAME} --policy-text file:///tmp/ecr-policy.json

echo -e "${GREEN}✓ Policies pushed. Waiting 10s for AWS propagation...${NC}"
sleep 10
echo -e "${GREEN}🚀 Security is now hot. You are clear for takeoff.${NC}"
rm /tmp/trust-policy.json /tmp/permissions-policy.json /tmp/ecr-policy.json