# Test Environment - Ready to Deploy

## ✅ What's Been Configured

### 1. **config.yaml** - Test Environment Block Added
```yaml
test:
  catalog_impl: "org.apache.iceberg.aws.glue.GlueCatalog"
  io_impl: "org.apache.iceberg.aws.s3.S3FileIO"
  warehouse: "s3://trading-pipeline-test/iceberg-warehouse/"
  raw_base_path: "s3://trading-pipeline-test/data/raw"
```

### 2. **config_manager.py** - Test Database Support
- Automatically uses `trading_db_test` when `ENV=test`
- No code changes needed when switching environments

### 3. **0_aws_pipeline_run_test.sh** - Test Orchestrator
- **Bootstrap mode** (default): Process ALL files in ONE EMR job
- **Batch mode** (`--batch`): Process 15 files at a time (for comparison)
- Uses `ENV=test` to route to test bucket

---

## 🚀 Quick Start

### Step 1: Create AWS Resources (One-time)
```bash
# Create test bucket
aws s3 mb s3://trading-pipeline-test

# Create directory structure
aws s3api put-object --bucket trading-pipeline-test --key data/raw/landing/
aws s3api put-object --bucket trading-pipeline-test --key data/raw/staging/
aws s3api put-object --bucket trading-pipeline-test --key data/raw/processed/

# Create test Glue database
aws glue create-database --database-input '{"Name": "trading_db_test"}'
```

### Step 2: Copy Test Data
```bash
# Option A: Copy 20 files for quick test (~30GB)
aws s3 ls s3://trading-pipeline/data/raw/processed/ | grep ".csv" | head -n 20 | awk '{print $4}' | while read f; do
    aws s3 cp "s3://trading-pipeline/data/raw/processed/$f" "s3://trading-pipeline-test/data/raw/landing/$f"
done

# Option B: Copy ALL 251 files for full performance test (~375GB)
aws s3 sync s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline-test/data/raw/landing/
```

### Step 3: Run Performance Test
```bash
# Single job approach (NEW - OPTIMIZED)
./0_aws_pipeline_run_test.sh

# Batch approach (OLD - BASELINE for comparison)
./0_aws_pipeline_run_test.sh --batch
```

---

## 📊 Expected Results

### Current Production Approach (17 jobs × 15 files)
- **Time**: 170-510 min (3-8.5 hours)
- **Issue**: Metadata accumulation slows each batch

### Optimized Test Approach (1 job × 251 files)
- **Time**: 45-90 min (0.75-1.5 hours)
- **Benefit**: 3-11x faster, single metadata commit

---

## 🔍 What Gets Tested

The test environment will validate:

1. ✅ **Single job processing** - All files in one EMR submission
2. ✅ **Iceberg metadata efficiency** - One metadata commit vs 17
3. ✅ **Spark task queueing** - 3,012 tasks queued, 4 concurrent (vCPU limit)
4. ✅ **Bronze/Silver table creation** - Fresh tables in `trading_db_test`
5. ✅ **No production impact** - Completely isolated test bucket

---

## 🛡️ Safety Guarantees

| Resource | Production | Test |
|----------|-----------|------|
| **S3 Bucket** | `trading-pipeline` | `trading-pipeline-test` |
| **Glue Database** | `trading_db` | `trading_db_test` |
| **Tables** | Bronze/Silver (existing) | Bronze/Silver (new) |
| **Data** | Untouched | Fresh copy |

**No risk to production data or tables.**

---

## 📝 Next Steps

1. **Review** `TEST_ENVIRONMENT_SETUP.md` for detailed instructions
2. **Run** Step 1 commands to create AWS resources
3. **Copy** test data (start with 20 files for quick validation)
4. **Execute** `./0_aws_pipeline_run_test.sh` (single job mode)
5. **Monitor** with `./infrastructure/watch_job.sh <job-run-id>`
6. **Compare** performance vs batch mode
7. **If successful**, apply changes to production `0_aws_pipeline_run.sh`

---

## 🧹 Cleanup (After Testing)

```bash
# Delete test bucket
aws s3 rb s3://trading-pipeline-test --force

# Delete test database
aws glue delete-database --name trading_db_test
```

---

## 📚 Documentation Files

- **`TEST_ENVIRONMENT_SETUP.md`** - Detailed step-by-step guide
- **`0_aws_pipeline_run_test.sh`** - Test pipeline orchestrator
- **`SWEEP.md`** - Original performance optimization plan

---

## ❓ Questions or Issues?

Refer to the Troubleshooting section in `TEST_ENVIRONMENT_SETUP.md` or check CloudWatch logs for the test EMR job.
