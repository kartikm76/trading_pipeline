# Test Environment Setup Guide

This guide walks you through setting up a test environment to safely test the performance optimizations without touching production data.

---

## Overview

**Production Environment:**
- S3 Bucket: `s3://trading-pipeline/`
- Glue Database: `trading_db`
- Tables: Bronze + Silver (already populated)

**Test Environment:**
- S3 Bucket: `s3://trading-pipeline-test/` (new)
- Glue Database: `trading_db_test` (new)
- Tables: Will be created fresh

---

## Step 1: Create Test S3 Bucket

```bash
# Create the test bucket
aws s3 mb s3://trading-pipeline-test

# Create directory structure
aws s3api put-object --bucket trading-pipeline-test --key data/raw/landing/
aws s3api put-object --bucket trading-pipeline-test --key data/raw/staging/
aws s3api put-object --bucket trading-pipeline-test --key data/raw/processed/
aws s3api put-object --bucket trading-pipeline-test --key iceberg-warehouse/

# Verify structure
aws s3 ls s3://trading-pipeline-test/ --recursive
```

---

## Step 2: Create Test Glue Database

```bash
# Create test database
aws glue create-database --database-input '{
  "Name": "trading_db_test",
  "Description": "Test environment for performance optimization testing"
}'

# Verify creation
aws glue get-database --name trading_db_test
```

---

## Step 3: Copy Sample Data to Test Bucket

You have two options:

### Option A: Copy a subset from production (recommended for quick test)
```bash
# Copy first 20 files from production to test landing zone
aws s3 ls s3://trading-pipeline/data/raw/processed/ | grep ".csv" | head -n 20 | awk '{print $4}' | while read f; do
    aws s3 cp "s3://trading-pipeline/data/raw/processed/$f" "s3://trading-pipeline-test/data/raw/landing/$f"
done

# Verify
aws s3 ls s3://trading-pipeline-test/data/raw/landing/ | wc -l
```

### Option B: Copy ALL files (for full performance test)
```bash
# WARNING: This copies all 251 files (~375GB)
aws s3 sync s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline-test/data/raw/landing/

# Verify
aws s3 ls s3://trading-pipeline-test/data/raw/landing/ | wc -l
```

---

## Step 4: Run Test Pipeline

### Bootstrap Mode (Single Job - Performance Test)
```bash
# Process ALL files in ONE EMR job
./0_aws_pipeline_run_test.sh

# This will:
# 1. Move all files from landing/ → staging/
# 2. Submit ONE EMR job with ENV=test
# 3. Process all files using bootstrap mode
# 4. Archive to processed/
```

### Batch Mode (Original Approach - Baseline)
```bash
# Process 15 files at a time (old approach for comparison)
./0_aws_pipeline_run_test.sh --batch
```

---

## Step 5: Monitor Performance

```bash
# Get job run ID from the script output, then:
./infrastructure/watch_job.sh <job-run-id>

# Or check manually:
aws emr-serverless get-job-run \
  --application-id $(cat .application-id) \
  --job-run-id <job-run-id> \
  --query 'jobRun.{state:state,duration:totalExecutionDurationSeconds}' \
  --output json
```

---

## Step 6: Verify Results

```bash
# Check table row counts in Athena
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM trading_db_test.bronze_options_chain" \
  --result-configuration "OutputLocation=s3://trading-pipeline-test/athena-results/" \
  --query-execution-context "Database=trading_db_test"

aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM trading_db_test.enriched_options_silver" \
  --result-configuration "OutputLocation=s3://trading-pipeline-test/athena-results/" \
  --query-execution-context "Database=trading_db_test"
```

---

## Expected Performance Improvements

**Current (Production - 251 files):**
- Approach: 17 EMR job submissions (15 files each)
- Time per batch: 10 min → 30 min (metadata accumulation)
- Total time: **170-510 min (~3-8.5 hours)**

**Optimized (Test - 251 files):**
- Approach: 1 EMR job submission (all files)
- Spark queues 3,012 tasks internally
- Total time: **45-90 min (~0.75-1.5 hours)**

**Expected Speedup: 3-11x faster**

---

## Cleanup Test Environment

When testing is complete and you want to remove the test environment:

```bash
# Delete S3 bucket and all contents
aws s3 rb s3://trading-pipeline-test --force

# Delete Glue database and all tables
aws glue delete-database --name trading_db_test
```

---

## Troubleshooting

### Issue: "Database trading_db_test does not exist"
```bash
# Recreate the database
aws glue create-database --database-input '{"Name": "trading_db_test"}'
```

### Issue: "Access Denied" errors
```bash
# Verify IAM role has permissions for the test bucket
# The role should already have S3 permissions from setup_iam_role.sh
# but it needs to include s3://trading-pipeline-test/*
```

### Issue: Tables not appearing in Glue
```bash
# List tables in test database
aws glue get-tables --database-name trading_db_test --query 'TableList[].Name'

# If empty but job succeeded, check CloudWatch logs for errors
```
