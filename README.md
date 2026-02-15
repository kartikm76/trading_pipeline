# Trading Pipeline

A production-grade options chain data pipeline built on **PySpark**, **Apache Iceberg**, and **AWS EMR Serverless**. Processes raw OPRA options data through a Medallion Architecture (Bronze → Silver → Gold) and generates trading signals via pluggable strategies.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [One-Time AWS Setup](#one-time-aws-setup)
- [Installation](#installation)
- [Running the Pipeline](#running-the-pipeline)
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

Configure your AWS credentials with access to the target account:
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

> **Note**: In dev mode, the pipeline reads CSVs from `data/raw/staging/`. Place your CSV files there before running dataload.

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
| `First-time load** (create tables from scratch)` | `ENV=dev uv run python src/main.py --mode dataload --bootstrap` | `./0_batch_pipeline.sh` |
| `Daily incremental load (append new data)`       | `ENV=dev uv run python src/main.py --mode dataload` | `./infrastructure/deploy_and_submit.sh daily` |
| `Regression test`                                | `./tests/regression_dataload.sh dev` | `./tests/regression_dataload.sh aws` |
| `Regression test (both envs)`                    | `./tests/regression_dataload.sh` | |
| `Regression + rebuild Docker image`              | `./tests/regression_dataload.sh --rebuild` | |

> **Dev note**: In dev mode, CSVs are read from `data/raw/staging/`. The batch script (`0_batch_pipeline.sh`) is AWS-only — it orchestrates S3 file movement between landing/staging/processed zones.

### 2. Strategy

Reads Silver tables and generates trading signals into **Gold**.

| Action                              | Dev (local) | AWS |
|-------------------------------------|---|---|
| `Run all active strategies`         | `ENV=dev uv run python src/main.py --mode strategy` | `./1_strategy_run.sh` |
| `Run a specific strategy`           | `ENV=dev uv run python src/main.py --mode strategy --strategies LaymanSPYStrategy` | `./1_strategy_run.sh --strategies LaymanSPYStrategy` |
| `Regression test`                   | `./tests/regression_strategy.sh dev` | `./tests/regression_strategy.sh aws` |
| `Regression test (both envs)`       | `./tests/regression_strategy.sh` | |
| `Regression + rebuild Docker image` | `./tests/regression_strategy.sh --rebuild` | |

> **`--strategies` flag**: Bypasses the `active: "Y"` check in `config.yaml`, letting you run any strategy without editing config. Without the flag, only strategies marked `active: "Y"` will run.

### Common Workflows

#### Data Loading

```bash
# First-time load (AWS) — loads all CSVs from S3 landing zone
./0_batch_pipeline.sh

# First-time load (local) — create local tables from CSVs in data/raw/staging/
ENV=dev uv run python src/main.py --mode dataload --bootstrap

# Dependency change — rebuild Docker image + run full dataload regression
./tests/regression_dataload.sh --rebuild
```

#### Strategy

```bash
# Day-to-day: code change → quick local check → deploy to AWS
./tests/regression_strategy.sh dev        # ~30s local sanity check
./1_strategy_run.sh                       # deploy to AWS

# Run strategies locally
ENV=dev uv run python src/main.py --mode strategy

# Dependency change — rebuild Docker image + run full strategy regression
./tests/regression_strategy.sh --rebuild
```

---

## Project Structure

```
trading_pipeline/
├── 0_batch_pipeline.sh              # Entry point: data loading (landing → bronze → silver)
├── 1_strategy_run.sh                # Entry point: strategy execution (silver → gold)
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

### Environment Blocks

The pipeline auto-selects the config block based on the `ENV` environment variable:

| ENV value | Config block | Set by | Catalog |
|-----------|-------------|--------|---------|
| `dev` (default) | `dev:` | You, locally | Local Hadoop |
| `aws` | `aws:` | EMR Serverless (via `.spark_config`) | AWS Glue + S3 |

### Strategy Switchboard

Toggle strategies on/off without code changes:

```yaml
strategies:
  - class: "LaymanSPYStrategy"
    active: "Y"              # ← Will run
    underlying: "SPY"
  - class: "IronCondorStrategy"
    active: "N"              # ← Skipped
    underlying: "SPY"
```

### Scaling

Resource allocation per run type (tuned for AWS vCPU quotas):

```yaml
scaling:
  bootstrap:
    max_executors: 4
    executor_memory: "16G"
    driver_memory: "16G"
  daily:
    max_executors: 2
    executor_memory: "8G"
    driver_memory: "8G"
```

---

## Adding a New Strategy

1. Create `src/strategies/my_strategy.py`:

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
        # Your Polars-based signal logic here
        return ldf.with_columns(
            pl.when(pl.col("mid_price") < 2.0)
              .then(pl.lit("BUY_CALL"))
              .otherwise(pl.lit("HOLD"))
              .alias("signal")
        )

    def generate_signals(self, df):
        pass  # Not used — logic() is the primary engine
```

2. Register in `src/strategies/__init__.py`
3. Add to `config.yaml`:
```yaml
strategies:
  - class: "MyStrategy"
    active: "Y"
    underlying: "SPY"
```
4. Run: `./1_strategy_run.sh`

The orchestrator will create a Gold table named `gold_mystrategy` automatically.

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
