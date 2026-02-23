# Test Environment Validation Plan

**Branch**: `optimization`
**Status**: Ready for testing
**Last Updated**: February 2025

---

## What's Already Done ✅

- [x] Created `optimization` branch with test environment config
- [x] Added `test:` environment block to `config.yaml`
- [x] Refactored `config_manager.py` to be environment-driven (no hardcoded if-blocks)
- [x] Created `0_aws_pipeline_run_test.sh` orchestrator script
- [x] Created `trading_db_test` Glue database (manually)
- [x] Created S3 bucket: `s3://trading-pipeline-test/`
- [x] Created folder structure:
  - `s3://trading-pipeline-test/data/raw/landing/`
  - `s3://trading-pipeline-test/data/raw/staging/`
  - `s3://trading-pipeline-test/data/raw/processed/`

---

## Pre-Testing Checklist

Before running tests, verify:

```bash
# Ensure you're on optimization branch
git branch
# Expected output: * optimization

# Verify config has test environment
grep -A 8 "^test:" config.yaml
# Expected: Should show test environment block with trading_db_test

# Verify test bucket exists
aws s3 ls s3://trading-pipeline-test/
# Expected: Shows the data/raw/ folder

# Verify test database exists
aws glue get-database --name trading_db_test
# Expected: Returns database info (no errors)
```

---

## Test Execution Plan

### Phase 1: Copy Test Data to Landing Zone

**Purpose**: Load sample CSV files for pipeline processing
**Time**: ~5-10 minutes

```bash
# Option A: QUICK TEST (3 files, ~1GB total, ~10-15 min job runtime)
aws s3 ls s3://trading-pipeline/data/raw/processed/ | grep ".csv" | head -n 3 | awk '{print $4}' | while read f; do
    echo "Copying $f..."
    aws s3 cp "s3://trading-pipeline/data/raw/processed/$f" "s3://trading-pipeline-test/data/raw/landing/$f"
done

# Verify files landed
aws s3 ls s3://trading-pipeline-test/data/raw/landing/
# Expected: 3 CSV files listed

# Option B: MEDIUM TEST (20 files, ~30GB total, ~30-45 min job runtime)
aws s3 ls s3://trading-pipeline/data/raw/processed/ | grep ".csv" | head -n 20 | awk '{print $4}' | while read f; do
    echo "Copying $f..."
    aws s3 cp "s3://trading-pipeline/data/raw/processed/$f" "s3://trading-pipeline-test/data/raw/landing/$f"
done

# Option C: FULL TEST (251 files, ~375GB total, ~45-90 min job runtime)
# ⚠️ WARNING: Only run this if you want full performance test
aws s3 sync s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline-test/data/raw/landing/

# Verify file count
FILE_COUNT=$(aws s3 ls s3://trading-pipeline-test/data/raw/landing/ | grep ".csv" | wc -l)
echo "Files in landing zone: $FILE_COUNT"
```

**Expected Result**: Files visible in `s3://trading-pipeline-test/data/raw/landing/`

---

### Phase 2: Run Test Pipeline (Single Job Mode)

**Purpose**: Validate that pipeline uses test environment, not production
**Time**: Depends on file count (10-90 minutes)

```bash
# Ensure you're on optimization branch
git status
# Expected: "On branch optimization"

# Run the test pipeline
./0_aws_pipeline_run_test.sh

# Script will:
# 1. Move files: landing/ → staging/
# 2. Submit EMR job with ENV=test
# 3. Create Bronze + Silver in trading_db_test
# 4. Move files: staging/ → processed/

# The script will output a job-run-id, save it:
# Job Run ID: 01ARJ1234567ABCD
```

**Expected Result**:
- Script completes successfully
- Files move through staging → processed
- No errors in pipeline

---

### Phase 3: Verification — Production Data Untouched

**Purpose**: Confirm production environment was NOT modified
**Time**: ~2 minutes

```bash
# ✅ CRITICAL: Verify production database unchanged
aws glue get-tables --database-name trading_db --query 'TableList[].Name'
# Expected: Only shows existing tables (bronze_options_chain, enriched_options_silver)
# DO NOT show any new tables

# ✅ Check production S3 bucket (should not have new data)
aws s3 ls s3://trading-pipeline/iceberg-warehouse/ --recursive | wc -l
# Expected: Same count as before (no new files added)

# ✅ Verify no test data in production landing zone
aws s3 ls s3://trading-pipeline/data/raw/landing/ | wc -l
# Expected: 0 files (unchanged)
```

**Expected Result**: Production data completely untouched ✅

---

### Phase 4: Verification — Test Environment Created Correctly

**Purpose**: Confirm test environment has new Bronze + Silver tables
**Time**: ~2 minutes

```bash
# ✅ Check test database has NEW tables
aws glue get-tables --database-name trading_db_test --query 'TableList[].Name'
# Expected output:
#   [
#     "bronze_options_chain",
#     "enriched_options_silver"
#   ]

# ✅ Verify test S3 warehouse has Iceberg metadata
aws s3 ls s3://trading-pipeline-test/iceberg-warehouse/ --recursive | head -20
# Expected: Files like:
#   iceberg-warehouse/trading_db_test/bronze_options_chain/metadata/
#   iceberg-warehouse/trading_db_test/enriched_options_silver/metadata/

# ✅ Verify files archived to processed zone
aws s3 ls s3://trading-pipeline-test/data/raw/processed/
# Expected: All CSV files moved here (empty staging, full processed)
```

**Expected Result**: Test database and warehouse properly populated ✅

---

### Phase 5: Query Test Tables via Athena

**Purpose**: Verify data was loaded correctly into test tables
**Time**: ~5 minutes

```bash
# Query 1: Bronze table row count
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) as row_count FROM trading_db_test.bronze_options_chain" \
  --result-configuration "OutputLocation=s3://trading-pipeline-test/athena-results/" \
  --query-execution-context "Database=trading_db_test"
# Copy the QueryExecutionId from output

# Get results (replace QUERY_ID with actual ID)
aws athena get-query-results --query-execution-id QUERY_ID
# Expected: row_count > 0

# Query 2: Silver table row count
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) as row_count FROM trading_db_test.enriched_options_silver" \
  --result-configuration "OutputLocation=s3://trading-pipeline-test/athena-results/" \
  --query-execution-context "Database=trading_db_test"

# Get results
aws athena get-query-results --query-execution-id QUERY_ID
# Expected: row_count > 0 (should be less than bronze due to filtering)

# Query 3: Date coverage in Silver
aws athena start-query-execution \
  --query-string "SELECT DISTINCT trade_date FROM trading_db_test.enriched_options_silver ORDER BY trade_date DESC LIMIT 5" \
  --result-configuration "OutputLocation=s3://trading-pipeline-test/athena-results/" \
  --query-execution-context "Database=trading_db_test"

# Get results
aws athena get-query-results --query-execution-id QUERY_ID
# Expected: Several dates shown (confirms data loaded)
```

**Expected Result**: Athena queries return data without errors ✅

---

## Success Checklist

### Environment Isolation ✅
- [ ] Production database `trading_db` unchanged
- [ ] Production S3 bucket `s3://trading-pipeline/` untouched
- [ ] Test database `trading_db_test` has new tables
- [ ] Test S3 bucket `s3://trading-pipeline-test/` has Iceberg metadata

### Data Flow ✅
- [ ] Files moved from landing/ → staging/ → processed/
- [ ] Bronze table created in `trading_db_test`
- [ ] Silver table created in `trading_db_test`
- [ ] Athena queries return row counts > 0

### Configuration ✅
- [ ] `ENV=test` routes to correct config block
- [ ] `config_manager.py` returns `trading_db_test` when ENV=test
- [ ] Test S3 paths point to `s3://trading-pipeline-test/`

---

## Troubleshooting

### Issue: "Database trading_db_test does not exist"
```bash
# Recreate it
aws glue create-database --database-input '{"Name": "trading_db_test"}'
```

### Issue: EMR job fails with "Access Denied"
```bash
# Verify IAM role has permissions for test bucket
# Re-run setup
./infrastructure/setup_iam_role.sh

# Add S3 permissions for test bucket if needed:
# - s3://trading-pipeline-test/*
# - s3://trading-pipeline-test/iceberg-warehouse/*
```

### Issue: Tables created in `trading_db` instead of `trading_db_test`
```bash
# Check if ENV=test is being passed correctly
echo "ENV=$ENV"
# Should show: ENV=test

# Check config_manager.py is reading test block
grep -A 5 "def db_name" src/config/config_manager.py
# Should use _get_env_specific()

# Verify config.yaml test block has db_name
grep -A 8 "^test:" config.yaml
# Should show: db_name: "trading_db_test"
```

### Issue: Iceberg metadata in production bucket instead of test
```bash
# Check raw_base_path and warehouse in test config block
grep -A 8 "^test:" config.yaml | grep -E "warehouse|raw_base_path"
# Should show:
#   warehouse: "s3://trading-pipeline-test/iceberg-warehouse/"
#   raw_base_path: "s3://trading-pipeline-test/data/raw"
```

### Issue: Job execution ID not shown
```bash
# Check infrastructure/deploy_and_submit.sh for output
# The last line should be: echo "Job Run ID: $JOB_RUN_ID"
# If not shown, check CloudWatch logs:
aws logs tail /aws/emr-serverless/jobs --follow
```

---

## Next Steps After Successful Validation

1. **Document Results**
   - Note job execution time
   - Compare with production baseline (17 jobs × 15 files)
   - Calculate speedup

2. **If Successful** (3-11x faster):
   - Merge `optimization` branch to `main`
   - Apply single-job approach to production `0_aws_pipeline_run.sh`
   - Run production dataload with optimization

3. **If Issues Found**:
   - Iterate on `optimization` branch
   - Fix issues
   - Re-test
   - Commit fixes

4. **Performance Optimization Next Steps** (per SWEEP.md):
   - Priority 2: Iceberg write tuning (Parquet file size, metadata cleanup)
   - Priority 3: Post-bootstrap compaction (rewrite_data_files, expire_snapshots)

---

## Important Notes

- **Do NOT delete test environment** until performance results are confirmed
- **Save job-run-id** for future reference/debugging
- **Test production dataload separately** after optimization is validated
- **All commands assume AWS CLI v2** is installed and configured
- **Ensure you have sufficient S3 storage** before running full test (375GB for 251 files)

---

## Git Commands Reference

```bash
# View current branch
git branch

# Switch to optimization branch
git checkout optimization

# View commits on this branch
git log --oneline -5

# Push latest changes
git push

# Create PR when ready
# https://github.com/kartikm76/trading_pipeline/pull/new/optimization
```

---

**Status**: Ready to test
**Contact**: Reach out if any issues during testing
