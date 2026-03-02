# Trading Pipeline

A production-grade options chain data pipeline built on **PySpark**, **Apache Iceberg**, and **AWS EMR Serverless**. Processes raw OPRA options data through a Medallion Architecture (Bronze → Silver → Gold) and generates trading signals via pluggable strategies.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [One-Time AWS Setup](#one-time-aws-setup)
- [Installation](#installation)
- [Running the Pipeline](#running-the-pipeline)
- [Full-Year Strategy Analysis](#full-year-strategy-analysis)
- [AWS vCPU Constraints](#aws-vcpu-constraints)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Adding a New Strategy](#adding-a-new-strategy)
- [Data Schema](#data-schema)
- [Monitoring & Debugging](#monitoring--debugging)
- [Useful Commands](#useful-commands)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
                        ┌──────────────────────────────────────────────┐
  CSV files             │           AWS EMR Serverless                 │
  (OPRA data)           │                                              │
       │                │   Bronze ──► Silver ──► Gold                 │
       ▼                │   (raw)     (enriched)   (signals)           │
  S3 Landing Zone ─────►│                                              │
                        │   Apache Iceberg tables in AWS Glue Catalog  │
                        └──────────────────────────────────────────────┘
                                          │
                                          ▼
                                  S3 Iceberg Warehouse
                                  (s3://trading-pipeline/)
```

| Layer | Table | Description |
|-------|-------|-------------|
| **Bronze** | `bronze_options_chain` | Raw CSV data, schema-preserved |
| **Silver** | `enriched_options_silver` | Decomposed OSI symbols, calculated mid-price, filtered |
| **Gold** | `gold_<strategyname>` | Trading signals (BUY_CALL / BUY_PUT / HOLD) per strategy |

---

## Prerequisites

| Tool | Version | Purpose | Install |
|------|---------|---------|---------|
| **Python** | 3.12+ | Runtime | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| **Java** | 11+ | PySpark engine | `brew install openjdk@11` |
| **uv** | latest | Python package manager | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **AWS CLI** | v2 | AWS operations | `brew install awscli` |
| **Docker Engine** | latest | Build EMR custom images | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or **Colima** (see below) |

### Docker Engine — Docker Desktop vs Colima

You need a Docker engine to build the custom EMR Serverless image. Either option works:

**Option A: Docker Desktop** (simplest)
```bash
# Install and launch Docker Desktop from https://www.docker.com/products/docker-desktop/
```

**Option B: Colima** (lightweight, no GUI, free for commercial use)
```bash
brew install colima docker docker-buildx

# Start Colima with buildx support
colima start --cpu 4 --memory 8 --arch aarch64

# Verify
docker info
docker buildx version
```

> **Note**: The pipeline builds multi-arch images (`amd64` + `arm64`) using `docker buildx`. Ensure buildx is available regardless of which engine you use.

### AWS Credentials

Configure AWS credentials with access to the target account:
```bash
aws configure
# Region: us-east-1
# Output: json
```

### Local Data Directories

For local development (`dev` mode), create the data folder structure:

```bash
mkdir -p data/raw/{landing,staging,processed}
```

| Directory | Purpose |
|-----------|---------|
| `data/raw/landing/` | Drop zone for new CSV files (local equivalent of S3 landing) |
| `data/raw/staging/` | Active processing zone — CSVs are read from here during dataload |
| `data/raw/processed/` | Archived CSVs after successful processing |

> **Note**: In dev mode, the pipeline reads CSVs from `data/raw/staging/`. Place CSV files there before running dataload.

---

## One-Time AWS Setup

These scripts only need to run once to provision the AWS infrastructure:

```bash
# 1. Create IAM role with S3, Glue, ECR, and CloudWatch permissions
./infrastructure/setup_iam_role.sh

# 2. Build the Docker image, push to ECR, and register with EMR app
./infrastructure/build_image.sh
```

> **When to re-run `build_image.sh`**: Only when you add/change pip dependencies in `pyproject.toml`. Code changes do NOT require a Docker rebuild — source code is shipped to S3 on every job submission.

---

## Installation

```bash
# Clone
git clone https://github.com/kartikm76/trading_pipeline.git
cd trading_pipeline

# Install all dependencies (creates .venv automatically)
uv sync
```

---

## Running the Pipeline

Two environments are available:

- **`dev`** — runs locally with PySpark (fast, no AWS needed)
- **`aws`** — submits a job to AWS EMR Serverless

### 1. Data Loading

Loads CSV files through **Landing → Bronze → Silver**.

| Action                                           | Dev (local) | AWS |
|--------------------------------------------------|---|---|
| `First-time load (create tables from scratch)`   | `./0_local_pipeline_run.sh` | `./0_aws_pipeline_run.sh` |
| `Daily incremental load (append new data)`       | `ENV=dev uv run python src/main.py --mode dataload` | `./infrastructure/deploy_and_submit.sh daily` |
| `Regression test`                                | `./tests/regression_dataload.sh dev` | `./tests/regression_dataload.sh aws` |
| `Regression test (both envs)`                    | `./tests/regression_dataload.sh` | |
| `Regression + rebuild Docker image`              | `./tests/regression_dataload.sh --rebuild` | |

> **Dev note**: Place CSV files in `data/raw/landing/`. The local script (`0_local_pipeline_run.sh`) handles the full `landing → staging → processed` lifecycle — just like `0_aws_pipeline_run.sh` does on AWS with S3.

### 2. Strategy

Reads Silver tables and generates trading signals into **Gold**.

| Action                              | Dev (local) | AWS |
|-------------------------------------|---|---|
| `Run all active strategies`         | `./1_local_strategy_run.sh` | `./1_aws_strategy_run.sh` |
| `Run a specific strategy`           | `./1_local_strategy_run.sh --strategies LaymanSPYStrategy` | `./1_aws_strategy_run.sh --strategies LaymanSPYStrategy` |
| `Regression test`                   | `./tests/regression_strategy.sh dev` | `./tests/regression_strategy.sh aws` |
| `Regression test (both envs)`       | `./tests/regression_strategy.sh` | |
| `Regression + rebuild Docker image` | `./tests/regression_strategy.sh --rebuild` | |

> **`--strategies` flag**: Bypasses the `active: "Y"` check in `config.yaml`, letting you run any strategy without editing config. Without the flag, only strategies marked `active: "Y"` will run.

### Common Workflows

#### Data Loading

```bash
# First-time load (local) — moves CSVs from landing/ → staging/ → processed/
./0_local_pipeline_run.sh

# First-time load (AWS) — loads all CSVs from S3 landing zone
./0_aws_pipeline_run.sh

# Dependency change — rebuild Docker image + run full dataload regression
./tests/regression_dataload.sh --rebuild
```

#### Strategy

```bash
# Day-to-day: code change → quick local check → deploy to AWS
./1_local_strategy_run.sh                 # run locally (~30s)
./1_aws_strategy_run.sh                   # deploy to AWS

# Run a specific strategy locally
./1_local_strategy_run.sh --strategies LaymanSPYStrategy

# Dependency change — rebuild Docker image + run full strategy regression
./tests/regression_strategy.sh --rebuild
```

---

## Full-Year Strategy Analysis

### Quick Start

Process the entire 2025 dataset (2.5B rows) with monthly batching:

```bash
# Run entire year with Iron Condor strategy
./2_yearly_strategy_analysis.sh

# Expected: 12 sequential jobs, ~2 hours total, $12-15 cost
# Result: gold_ironcondorstrategy table with all 2.5B rows analyzed
```

### How It Works

The framework automatically adapts execution strategy based on configuration:

**Batch Modes:**
- **Snapshot** (default for Iron Condor): Monthly batching with no lookback
  - 12 parallel-capable jobs (limited by AWS quota)
  - Each processes ~200M rows in ~10 minutes

- **Lookback** (for momentum, IV analysis): Sliding windows with overlapping buffers
  - Sequential execution (dependencies between batches)
  - Each batch includes prior N days for context

- **Full**: Single large job for entire dataset
  - All 2.5B rows in one job with enhanced resources
  - ~90 minutes, $20-25

### Common Commands

```bash
# Full year (sequential, default - works with 16 vCPU quota)
./2_yearly_strategy_analysis.sh

# Specific year
./2_yearly_strategy_analysis.sh 2024

# Force batch mode
./2_yearly_strategy_analysis.sh --snapshot
./2_yearly_strategy_analysis.sh --lookback
./2_yearly_strategy_analysis.sh --full

# Control parallelism (requires AWS quota increase)
./2_yearly_strategy_analysis.sh --max-jobs 1   # Sequential (~2 hours)
./2_yearly_strategy_analysis.sh --max-jobs 4   # Parallel (~30 min) - needs 64 vCPU

# Single monthly batch
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 --end-date 2025-02-01

# Verify results
spark-sql> SELECT COUNT(*), COUNT(DISTINCT trade_date)
           FROM gold_ironcondorstrategy;
# Expected: ~2.5B rows, 252 distinct dates (no duplicates)
```

### Monthly Batching Details

```
The 2025 dataset:  2.5B rows, 252 trading days

Monthly batching:
  Jan batch  → ~208M rows in ~10 min
  Feb batch  → ~188M rows in ~10 min
  ...
  Dec batch  → ~208M rows in ~10 min

Total: 12 jobs, ~200M rows each

Execution timeline (sequential):
  - Jobs run ONE at a time (AWS 16 vCPU quota limit)
  - Wall time: 12 × 10 min = ~120 min (~2 hours)
  - Cost: ~$1-1.50 per job = $12-15 total

Execution timeline (if quota increased to 64 vCPU):
  - Run 4 jobs in parallel
  - Wall time: 3 × 10 min = ~30 min
  - Cost: Same $12-15 total
```

### Non-Overlapping Output Guarantee

For lookback strategies (e.g., momentum), batches have overlapping input but non-overlapping output:

```
Batch 1 (Jan with 5-day lookback):
  Input:  Dec 27-31 + Jan 1-31  (buffer + decision dates)
  Output: Jan 1-31 only (discards Dec buffer)

Batch 2 (Feb with 5-day lookback):
  Input:  Jan 27-31 + Feb 1-28  (buffer + decision dates)
  Output: Feb 1-28 only (discards Jan overlap)

Result: Gold table has each date exactly once ✓
```

### Monitoring & Logs

```bash
# Watch batch progress
tail -f logs/yearly_analysis/yearly_analysis_2025_*.log

# Check progress
grep "Progress" logs/yearly_analysis/yearly_analysis_2025_*.log

# Look for failures
grep "❌ Failed" logs/yearly_analysis/yearly_analysis_2025_*.log

# Retry a failed batch
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-02-01 --end-date 2025-03-01
```

### What Gets Generated

Gold table: `gold_ironcondorstrategy`

Columns:
- `underlying` (SPY)
- `trade_date` (2025-01-01, 2025-01-02, ...)
- `expiration` (option expiry date)
- `strike_short_call`, `price_short_call`
- `strike_long_call`, `price_long_call`
- `strike_short_put`, `price_short_put`
- `strike_long_put`, `price_long_put`
- `net_credit` (positive = profitable condor)
- `strategy_name` (IRON_CONDOR)

Total: ~2.5B rows, 252 partitions (by trade_date), Iceberg format on S3

---

## AWS vCPU Constraints

### The Issue

**Personal AWS accounts have a 16 vCPU hard quota by default.**

Configuration:
```yaml
snapshot:
  max_executors: 4           # 4 executors
  executor_memory: "16G"
```

vCPU calculation:
```
4 executors × 4 vCPU per executor = 16 vCPU per job
```

**Result:** Only **1 job can run at a time** (sequential execution).

### Default Execution

**Before:** 12 parallel jobs, ~20 min ❌ (exceeds quota)
**Now:** 12 sequential jobs, ~120 min ✅ (works with default quota)

```bash
./2_yearly_strategy_analysis.sh
# Runs one batch at a time
# Time: 12 batches × ~10 min = ~120 min (~2 hours)
# Cost: $12-15 (same total compute, just sequential)
```

### To Enable Parallelism

**Option 1: Request AWS Quota Increase** (Recommended)

```bash
# 1. Go to AWS Service Quotas Console
# 2. Search for "EMR Serverless"
# 3. Find "vCPU" quota
# 4. Request increase:
#    - For 2 parallel jobs: 32 vCPU
#    - For 4 parallel jobs: 64 vCPU
# 5. AWS usually approves within hours/days (often auto-approved)

# Then run:
./2_yearly_strategy_analysis.sh --max-jobs 4
# Time: ~30 min (4 jobs in parallel)
```

**Option 2: Reduce Executors per Job** (Slower)

```yaml
# In config.yaml, change:
snapshot:
  max_executors: 2    # Instead of 4
```

```bash
# Then can run 2 jobs in parallel
./2_yearly_strategy_analysis.sh --max-jobs 2
# Each job takes ~20 min (slower), but works within quota
```

### AWS vCPU Requirements by Scenario

| Scenario | vCPU Needed | Works Default? | Action |
|----------|-------------|---|--------|
| Sequential (1 job) | 16 vCPU | ✅ YES | Just run! |
| 2 jobs parallel | 32 vCPU | ❌ NO | Request increase |
| 4 jobs parallel | 64 vCPU | ❌ NO | Request increase |
| 12 jobs parallel (original) | 192 vCPU | ❌ NO | Not feasible |

### Check Current Quota

```bash
aws service-quotas get-service-quota \
  --service-code emr-serverless \
  --quota-code vCPU \
  --query 'Quota.Value' --output text

# Should return: 16 (default)
```

### Performance Benchmarks

| Scenario | Time | Cost | Notes |
|----------|------|------|-------|
| 1 day | ~5 min | $1 | |
| 1 month | ~10 min | $2 | |
| Full year (sequential) | ~120 min | $12-15 | ✅ Default, no quota increase |
| Full year (2 parallel) | ~60 min | $12-15 | Needs 32 vCPU quota increase |
| Full year (4 parallel) | ~30 min | $12-15 | Needs 64 vCPU quota increase |

**Note:** Cost is identical for all scenarios — only wall time changes.

---

## Project Structure

```
trading_pipeline/
├── 0_aws_pipeline_run.sh            # Entry point: AWS data loading (landing → bronze → silver)
├── 0_local_pipeline_run.sh          # Entry point: local dev data loading (same flow, local filesystem)
├── 1_aws_strategy_run.sh            # Entry point: AWS strategy execution (silver → gold)
├── 1_local_strategy_run.sh          # Entry point: local dev strategy execution
├── config.yaml                      # All pipeline configuration
├── Dockerfile                       # Custom EMR image (Python 3.12 + pip deps)
├── pyproject.toml                   # Python dependencies
│
├── data/                            # Local data directories (dev mode only)
│   └── raw/
│       ├── landing/                 # Drop zone for new CSV files
│       ├── staging/                 # Active processing zone (CSVs read from here)
│       └── processed/               # Archived CSVs after successful processing
│
├── src/
│   ├── main.py                      # CLI entry point (--mode dataload|strategy)
│   ├── config/
│   │   ├── config_manager.py        # YAML config loader, env-aware (dev/aws)
│   │   └── spark_session.py         # SparkSession builder (local/aws)
│   ├── adapters/                    # Data ingestion (CSV, Parquet, API)
│   ├── filters/                     # Silver-layer filter policies
│   ├── services/
│   │   ├── data_load_orchestrator.py    # Bronze + Silver pipeline
│   │   ├── strategy_orchestrator.py     # Gold pipeline (parallel strategy execution)
│   │   └── silver_enricher.py           # OSI symbol decomposition + mid-price calc
│   ├── strategies/
│   │   ├── base_strategy.py             # Abstract base (Spark → Polars → Spark)
│   │   ├── strategy_factory.py          # Instantiates strategies from config
│   │   ├── layman_spy_strategy.py       # Simple mid-price signal strategy
│   │   └── iron_condor_strategy.py      # Iron condor spread strategy
│   └── utils/                       # Helpers (data gen, Iceberg setup, etc.)
│
├── infrastructure/                  # AWS deployment scripts (each does ONE thing)
│   ├── env_discovery.sh             # Shared AWS env vars (account, region, app ID)
│   ├── .spark_config                # Spark submit parameters
│   ├── build_image.sh               # Build + push Docker image + update EMR app
│   ├── deploy_and_submit.sh         # Package code → upload S3 → submit EMR job
│   ├── watch_job.sh                 # Monitor a running EMR job
│   ├── setup_iam_role.sh            # One-time IAM role & permissions setup
│   └── terminate_all.sh             # Teardown all AWS resources
│
└── tests/
    ├── regression_strategy.sh       # Strategy regression (dev + aws)
    ├── regression_dataload.sh        # Dataload regression (dev + aws)
    ├── inspect_tables.py
    └── test_spark.py
```

---

## Configuration

All settings live in **`config.yaml`**. Key sections:

### Strategy Organization by Batch Mode

Strategies are organized by execution mode to determine how they run:

```yaml
strategies:
  # Snapshot: Monthly batching, parallel execution (if quota allows)
  # No lookback needed — decisions from single trade_date snapshot
  snapshot:
    - class: "IronCondorStrategy"
      active: "Y"
      underlying: "SPY"
      lookback_days: 0
      output_mode: "non_overlapping"
      group_key: ["underlying", "trade_date", "expiry_date"]

  # Lookback: Sliding windows, sequential execution
  # Needs prior N days for context (momentum, IV percentile, etc.)
  lookback:
    # Example (disabled for now):
    # - class: "MomentumStrategy"
    #   active: "Y"
    #   underlying: "SPY"
    #   lookback_days: 5
    #   output_mode: "non_overlapping"

  # Full: Single large job for entire dataset
  # Requires full visibility (correlation, position tracking, etc.)
  full:
    # Example (disabled for now):
    # - class: "CorrelationArbitrageStrategy"
    #   active: "Y"
    #   underlying: "SPY"
    #   lookback_days: 252
```

### Environment Blocks

The pipeline auto-selects the config block based on the `ENV` environment variable:

| ENV value | Config block | Set by | Catalog |
|-----------|-------------|--------|---------|
| `dev` (default) | `dev:` | You, locally | Local Hadoop |
| `aws` | `aws:` | EMR Serverless (via `.spark_config`) | AWS Glue + S3 |

### Scaling

Resource allocation per run type (tuned for AWS vCPU quotas):

```yaml
scaling:
  bootstrap:
    max_executors: 4
    executor_memory: "16G"
    driver_memory: "16G"
  daily:
    max_executors: 4
    executor_memory: "16G"
    driver_memory: "16G"
  # Snapshot strategies (monthly batching)
  snapshot:
    max_executors: 4
    executor_memory: "16G"
    driver_memory: "16G"
    shuffle_partitions: 200
  # Lookback strategies (sliding windows)
  lookback:
    max_executors: 4
    executor_memory: "16G"
    driver_memory: "16G"
    shuffle_partitions: 200
  # Full dataset strategies
  full:
    max_executors: 8
    executor_memory: "32G"
    driver_memory: "32G"
    shuffle_partitions: 500
```

> **Note:** Snapshot strategies default to 4 executors × 16GB = 16 vCPU per job, which matches the AWS personal account quota. For parallelism, request a quota increase.

---

## Adding a New Strategy

### Step 1: Create Strategy Class

Create `src/strategies/my_strategy.py`:

```python
import polars as pl
from strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    lookback_days = 7  # How many days of data to process

    @property
    def required_columns(self):
        return ["symbol", "trade_date", "expiry_date", "strike_price",
                "mid_price", "option_type"]

    def logic(self, ldf: pl.LazyFrame) -> pl.LazyFrame:
        # Polars-based signal logic here
        return ldf.with_columns(
            pl.when(pl.col("mid_price") < 2.0)
              .then(pl.lit("BUY_CALL"))
              .otherwise(pl.lit("HOLD"))
              .alias("signal")
        )

    def generate_signals(self, df):
        pass  # Not used — logic() is the primary engine
```

### Step 2: Register Strategy

Add to `src/strategies/__init__.py`:

```python
from .my_strategy import MyStrategy
```

### Step 3: Add to config.yaml

Determine batch mode based on strategy needs:

```yaml
# If no lookback needed (snapshot strategy):
strategies:
  snapshot:
    - class: "MyStrategy"
      active: "Y"
      underlying: "SPY"
      lookback_days: 0
      output_mode: "non_overlapping"
      group_key: ["underlying", "trade_date"]

# OR if it needs prior N days (lookback strategy):
strategies:
  lookback:
    - class: "MyStrategy"
      active: "Y"
      underlying: "SPY"
      lookback_days: 5
      output_mode: "non_overlapping"
      group_key: ["underlying", "trade_date"]

# OR if it needs entire dataset (full strategy):
strategies:
  full:
    - class: "MyStrategy"
      active: "Y"
      underlying: "SPY"
      lookback_days: 252
      output_mode: "non_overlapping"
      group_key: ["underlying"]
```

### Step 4: Run

The orchestrator automatically:
- Detects batch mode from config
- Creates gold table named `gold_mystrategy`
- Handles all batching, windowing, and output filtering

```bash
# Run locally
./1_local_strategy_run.sh

# Or deploy to AWS
./1_aws_strategy_run.sh
```

### Batch Mode Selection Guide

| Mode | Use When | Example |
|------|----------|---------|
| **snapshot** | No lookback needed, single trade_date decisions | Iron Condor, Calendar Spreads |
| **lookback** | Need prior N days for context | Momentum, IV Percentile, Technical Indicators |
| **full** | Need entire dataset visibility | Correlation, Position Tracking, Greeks Curves |

---

## Data Schema

### Silver Table — `enriched_options_silver`

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | string | OSI symbol (e.g., `SPX   250221C01000000`) |
| `underlying` | string | Mapped tradeable ETF (e.g., `SPY`) |
| `trade_date` | date | Trading date (from filename) |
| `expiry_date` | date | Option expiration (from symbol) |
| `option_type` | string | `CALL` or `PUT` |
| `strike_price` | decimal(10,2) | Strike price |
| `mid_price` | decimal(10,2) | `(bid_px_00 + ask_px_00) / 2` |
| `bid_px_00` / `ask_px_00` | double | Best bid/ask prices |
| `bid_sz_00` / `ask_sz_00` | integer | Best bid/ask sizes |
| `ts_recv` / `ts_event` | timestamp | Receive / event timestamps |
| `file_name` | string | Source CSV filename |

### Gold Table — `gold_<strategyname>`

Inherits all Silver columns plus:

| Column | Type | Description |
|--------|------|-------------|
| `signal` | string | `BUY_CALL`, `BUY_PUT`, or `HOLD` |
| `strategy_name` | string | Strategy class name |

---

## Monitoring & Debugging

```bash
# Watch a running job (polls every 10s)
./infrastructure/watch_job.sh <job-run-id>

# One-shot status check
aws emr-serverless get-job-run \
  --application-id $(cat .application-id) \
  --job-run-id <job-run-id> \
  --query 'jobRun.{state:state,details:stateDetails}' --output json

# Spark UI dashboard
aws emr-serverless get-dashboard-for-job-run \
  --application-id $(cat .application-id) \
  --job-run-id <job-run-id> --query 'url' --output text
```

### Query Gold Tables via Athena

```sql
-- Signal distribution
SELECT trade_date, signal, COUNT(*) as cnt
FROM trading_db.gold_laymanspystrategy
GROUP BY trade_date, signal
ORDER BY trade_date DESC;

-- Silver table date coverage
SELECT trade_date, COUNT(*) as records
FROM trading_db.enriched_options_silver
GROUP BY trade_date ORDER BY trade_date DESC;
```

---

## Useful Commands

### S3 File Management

```bash
# Upload CSVs to landing zone
aws s3 cp /local/path/*.csv s3://trading-pipeline/data/raw/landing/

# Check file counts per zone
aws s3 ls s3://trading-pipeline/data/raw/landing/   | wc -l
aws s3 ls s3://trading-pipeline/data/raw/staging/   | wc -l
aws s3 ls s3://trading-pipeline/data/raw/processed/ | wc -l

# Reprocess: move archived files back to landing
aws s3 mv s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline/data/raw/landing/ --recursive
```

### Glue Table Management

```bash
# List tables
aws glue get-tables --database-name trading_db --query 'TableList[].Name'

# Drop a table (for clean restart)
aws glue delete-table --database-name trading_db --name bronze_options_chain

# Clean Iceberg warehouse
aws s3 rm s3://trading-pipeline/iceberg-warehouse/ --recursive
```

### Infrastructure

```bash
# Rebuild Docker image (only when pip deps change)
./infrastructure/build_image.sh

# Teardown all AWS resources (EMR app + IAM role)
./infrastructure/terminate_all.sh
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Java not found` | `brew install openjdk@11` and set `export JAVA_HOME=$(/usr/libexec/java_home -v 11)` |
| `Module not found` errors (local) | Use `uv run python src/main.py` not `python src/main.py` |
| `Table already exists` | Run with `--bootstrap` to recreate tables |
| `ServiceQuotaExceededException: vCPU` | Reduce `max_executors` in config.yaml or request AWS quota increase |
| `AccessDeniedException: glue:CreateTable` | Re-run `./infrastructure/setup_iam_role.sh` to update IAM permissions |
| `can't open file '/app/src/main.py'` | Entry point must be S3-based (`s3://`), not container path. Check `deploy_and_submit.sh` |
| `No module named 'distutils'` | Pin project to Python 3.12: `uv python pin 3.12 && uv sync --reinstall` |
| `RecursionError: Stack overflow in comparison` | PySpark incompatible with Python 3.14. Use Python 3.12 (see above) |
| Docker build fails | Ensure Docker/Colima is running: `docker info`. For Colima: `colima start` |
| Version conflicts | `uv sync --reinstall` |
