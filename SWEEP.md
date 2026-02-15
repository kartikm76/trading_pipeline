# Trading Pipeline - Development Notes

## Quick Start — Daily Workflow
```bash
# Edit your strategy code, then ONE command to deploy & run:
./infrastructure/deploy_and_submit.sh "strategy"

# Other modes:
./infrastructure/deploy_and_submit.sh "bootstrap"   # initial data load
./infrastructure/deploy_and_submit.sh "daily"        # daily data load
```
This automatically packages source code, uploads to S3, and submits the EMR job.

## Only Rebuild Docker When Adding New pip Dependencies
```bash
# 1. Update pyproject.toml with new dependency
# 2. Rebuild, push, and update EMR app (all-in-one)
./infrastructure/build_image.sh
```

## Monitoring
```bash
# Watch a running job
./infrastructure/watch_job.sh <job-run-id>

# Check job status
aws emr-serverless get-job-run --application-id 00g35nv23d1lkf09 \
  --job-run-id <job-run-id> \
  --query 'jobRun.{state:state,stateDetails:stateDetails}' --output json

# Get Spark UI dashboard URL
aws emr-serverless get-dashboard-for-job-run --application-id 00g35nv23d1lkf09 \
  --job-run-id <job-run-id> --query 'url' --output text
```

## EMR Serverless Architecture Notes
- **Application ID**: 00g35nv23d1lkf09 (OptionTradingApp)
- **Release**: emr-7.11.0 | **Architecture**: ARM64
- **Docker image**: Python 3.12 + pip dependencies ONLY
- **Source code**: Shipped via `--py-files` (S3 zip) — fast iteration, no rebuild needed
- **config.yaml**: Shipped via `--files` to working directory
- **Entry point**: `s3://trading-pipeline/artifacts/main.py`
- **WORKDIR**: Must remain `/home/hadoop` | **USER**: Must be `hadoop:hadoop`
- **Image updates**: Must stop app → update → restart to pick up new image digest
- **vCPU quota**: Keep executor count reasonable (currently 2×8G for daily)

## 🔖 PARKED: Batch Pipeline Performance Optimization
**Status**: Parked — data already loaded in silver tables, revisit later.
**Problem**: 251 files × 1.5GB each, batched in groups of 15 → 17 EMR job submissions.
Job time grew from 10 min → 30 min due to Iceberg metadata accumulation per batch.
**AWS Constraint**: 16 vCPU hard limit → max 4 executors.

**Plan (in priority order):**
1. **Single bootstrap job** — Process all 251 files in ONE EMR job instead of 17.
   Spark queues 3,012 tasks internally, runs 4 at a time. ~45-90 min vs 170-510 min.
   Change: Remove shell loop in `0_batch_pipeline.sh` for bootstrap mode.
2. **Iceberg write tuning** — Add table properties to reduce file/metadata bloat:
   - `write.target-file-size-bytes = 536870912` (512MB files)
   - `write.distribution-mode = hash`
   - `write.metadata.delete-after-commit.enabled = true`
   - `write.metadata.previous-versions-max = 3`
3. **Post-bootstrap compaction** — Run Iceberg maintenance after bulk load:
   - `rewrite_data_files()` — compact small files into ~512MB
   - `rewrite_manifests()` — compact manifest files
   - `expire_snapshots()` — remove old snapshot metadata
   - Implement as `2_maintenance.sh` or `--mode maintenance` in main.py
4. **In-Spark batching (optional)** — If checkpoint/resume needed, move loop inside
   Python code instead of shell. One EMR job, loop over batches internally.

## Key Files
**Top-level entry points:**
- `0_batch_pipeline.sh` - Data loading orchestrator (landing → bronze → silver)
- `1_strategy_run.sh` - Strategy execution entry point

**Infrastructure helpers (each does ONE thing):**
- `infrastructure/build_image.sh` - Build + push Docker image + update EMR app (full image lifecycle)
- `infrastructure/deploy_and_submit.sh` - Package code → upload S3 → submit EMR job
- `infrastructure/.spark_config` - Spark submit parameters
- `infrastructure/env_discovery.sh` - Shared AWS environment variables
- `infrastructure/watch_job.sh` - Monitor a running EMR job
- `infrastructure/setup_iam_role.sh` - One-time IAM role & permissions setup
- `infrastructure/terminate_all.sh` - Teardown all AWS resources

**Config:**
- `Dockerfile` - Custom EMR image (Python 3.12 + pip deps only)
- `config.yaml` - Application configuration (scaling, strategies, etc.)
