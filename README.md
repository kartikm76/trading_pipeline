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

> **👉 See [PIPELINE_EXECUTION.md](PIPELINE_EXECUTION.md) for all commands, parameters, and troubleshooting**

Two environments are available:

- **`dev`** — runs locally with PySpark (fast, no AWS needed)
- **`aws`** — submits a job to AWS EMR Serverless

### Quick Start

```bash
# Daily strategy run (latest data)
./infrastructure/deploy_and_submit.sh strategy

# Full year 2025 (all 12 months)
./2_yearly_strategy_analysis.sh --year 2025

# Single month test
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 --end-date 2025-02-01 --clear-existing
```

For detailed commands, parameters, and troubleshooting → **[PIPELINE_EXECUTION.md](PIPELINE_EXECUTION.md)**

---

## Full-Year Strategy Analysis

> **👉 For commands, parameters, and troubleshooting, see [PIPELINE_EXECUTION.md](PIPELINE_EXECUTION.md)**

Process the entire 2025 dataset (2.5B rows) with monthly batching:

```bash
./2_yearly_strategy_analysis.sh --year 2025
# 12 sequential jobs, ~2 hours, $12-15 total cost
```

**Key points:**
- Automatically batches by month (~200M rows each, ~10 min per batch)
- Respects AWS 16 vCPU quota (sequential by default)
- Non-overlapping output — each trade_date appears exactly once
- Iceberg partitioned on S3

**Result:** `gold_ironcondorstrategy` table (~2.5B rows, 252 trade_dates)

---

## AWS vCPU Constraints

> **👉 For detailed explanation and quota increase procedures, see [PIPELINE_EXECUTION.md](PIPELINE_EXECUTION.md)**

**Personal AWS accounts have a 16 vCPU quota by default.**

With 4 executors × 4 vCPU = 16 vCPU per job, only **1 job runs at a time**.

The pipeline respects this by default:
```bash
./2_yearly_strategy_analysis.sh --year 2025
# Runs 12 batches sequentially (~2 hours, $12-15)
```

To parallelize (optional): Request AWS quota increase to 64 vCPU, then:
```bash
./2_yearly_strategy_analysis.sh --year 2025 --max-jobs 4
# Runs 4 jobs in parallel (~30 min, same $12-15 cost)
```

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

## Development Workflow

### Daily: Edit Code → Deploy → Test

```bash
# 1. Edit your strategy code
# 2. Run one command to package, upload, and test:
./infrastructure/deploy_and_submit.sh strategy

# Other modes:
./infrastructure/deploy_and_submit.sh bootstrap   # Initial data load
./infrastructure/deploy_and_submit.sh daily       # Daily data load
```

### Adding New Python Dependencies

```bash
# 1. Update pyproject.toml with new dependency
# 2. Rebuild Docker image and update EMR app:
./infrastructure/build_image.sh

# 3. Run regression tests to verify:
./tests/regression_strategy.sh
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
