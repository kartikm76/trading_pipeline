# Trading Pipeline - Options Chain Data Processing

A production-ready data pipeline for processing options chain data using PySpark, Apache Iceberg, and the Medallion Architecture (Bronze → Silver → Gold).

## 📋 Table of Contents
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Running the Pipeline](#-running-the-pipeline)
- [Batch Processing (Production)](#-batch-processing-production)
- [Inspecting Data](#-inspecting-data)
- [Data Schema](#-data-schema)
- [Troubleshooting](#-troubleshooting)
- [Pipeline Stages](#-pipeline-stages)
- [Customization](#-customization)

---

## 🔧 Prerequisites

Before you begin, make sure you have the following installed on your machine:

### 1. **Python 3.12 or higher**
Check if Python is installed:
```bash
python3 --version
```

If not installed, download from [python.org](https://www.python.org/downloads/)

### 2. **Java 11 or higher** (Required for PySpark)
Check if Java is installed:
```bash
java -version
```

If not installed:
- **Mac**: `brew install openjdk@11`
- **Linux**: `sudo apt-get install openjdk-11-jdk`
- **Windows**: Download from [Oracle](https://www.oracle.com/java/technologies/downloads/)

### 3. **uv** (Python Package Manager)
Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or on Mac:
```bash
brew install uv
```

Verify installation:
```bash
uv --version
```

---

## 📥 Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/kartikm76/trading_pipeline.git
cd trading_pipeline
```

### Step 2: Install Dependencies
The project uses `uv` for dependency management. All dependencies are defined in `pyproject.toml`.

```bash
# Install all dependencies and create virtual environment
uv sync
```

This will:
- Create a virtual environment (`.venv`)
- Install all required packages (PySpark, PyArrow, etc.)
- Set up the project for development

---

## 📁 Project Structure

```
trading_pipeline/
├── src/
│   ├── adapters/          # Data ingestion adapters (CSV, Parquet, API)
│   ├── config/            # Configuration management
│   ├── filters/           # Data filtering policies
│   ├── models/            # Data models
│   ├── services/          # Core business logic (orchestrator, enricher)
│   ├── strategies/        # Trading signal generation strategies
│   ├── utils/             # Utility functions
│   └── main.py            # Main entry point
├── infrastructure/        # AWS deployment and automation scripts
│   ├── 1_setup_iam_role.sh       # Creates IAM roles for EMR Serverless
│   ├── 2_deploy_and_submit.sh   # Deploys code and submits Spark jobs
│   ├── 3_watch_job.sh            # Monitors running EMR jobs
│   ├── 9_terminate_all.sh        # Cleanup script
│   └── dist/                     # Build artifacts (auto-generated)
├── tests/                 # Test scripts
│   └── inspect_tables.py  # View table schemas and data
├── data/
│   ├── raw/
│   │   ├── landing/       # [S3] Incoming CSV files (bulk upload)
│   │   ├── staging/       # [S3] Files being processed by Spark
│   │   └── processed/     # [S3] Successfully processed files (archive)
│   └── iceberg-warehouse/ # [Local/S3] Iceberg table storage
├── batch_control.sh       # Automated batch processing controller
├── config.yaml            # Main configuration file
├── pyproject.toml         # Project dependencies
└── README.md              # This file
```

---

## ⚙️ Configuration

### 1. **config.yaml**
This file controls all pipeline settings. Key sections:

```yaml
project:
  environment: "dev"  # or "prod"

storage:
  catalog_name: "glue_catalog"
  db_name: "trading_db"
  tables:
    bronze: "bronze_options_chain"
    silver: "enriched_options_silver"
    gold: "trading_signals_gold"

data_format:
  raw: "csv"           # Format of input data
  iceberg: "parquet"   # Format for Iceberg tables

dev:
  warehouse: "./iceberg-warehouse"
  raw_data_path: "./data/raw/opra-pillar-20250128.cbbo-1m.csv"

strategies:
  - class: "LaymanSPYStrategy"
    active: "Y"
    underlying: "SPY"

filters:
  - class: "ZeroDTEPolicy"
    active: "N"
  - class: "LiquidityPolicy"
    active: "N"
```

### 2. **Place Your Data**
Put your raw CSV file in the `data/raw/` directory:
```bash
mkdir -p data/raw
# Copy your CSV file here
cp /path/to/your/data.csv data/raw/
```

Update `config.yaml` to point to your file:
```yaml
dev:
  raw_data_path: "./data/raw/your-file.csv"
```

---

## 🚀 Running the Pipeline

### First Time Setup (Bootstrap Mode)
Bootstrap mode creates all tables from scratch:

```bash
ENV=dev 
uv run python src/main.py --bootstrap
```

This will:
1. ✅ Create Iceberg catalog and database
2. ✅ Ingest raw CSV data → Bronze table
3. ✅ Enrich and filter data → Silver table
4. ✅ Generate trading signals → Gold table

**Expected Output:**
```
Setting up Iceberg infrastructure...
Creating catalog: glue_catalog
Creating database: trading_db
Ingesting data from CSV...
Processing 10M+ records...
--- [Orchestration] Gold table glue_catalog.trading_db.trading_signals_gold created ---
```

### Incremental Updates (Append Mode)
For daily updates without recreating tables:

```bash
ENV=dev 
uv run python src/main.py
```

---

## 🔄 Batch Processing (Production)

### Overview

The `batch_control.sh` script automates bulk file processing for production environments. It orchestrates the complete workflow:

**Landing → Staging → Processing → Archive**

### How It Works

1. **Landing Zone**: Upload multiple CSV files to `s3://trading-pipeline/data/raw/landing/`
2. **Batch Processing**: Script processes files in batches of 15
3. **Staging**: Files are moved to `staging/` during processing
4. **Archive**: Successfully processed files move to `processed/`
5. **Incremental Mode**: First batch runs in `bootstrap` mode, subsequent batches run in `daily` (append) mode

### Usage

#### Production (AWS EMR Serverless)
```bash
./batch_control.sh prod
```

#### Local Development
```bash
./batch_control.sh dev
```

### Workflow Phases

| Phase | Mode | Action | Table Operation |
|-------|------|--------|-----------------|
| **Batch 1** (First 15 files) | `bootstrap` | Uploads code + processes data | `createOrReplace` (clean start) |
| **Batch 2** (Next 15 files) | `daily` | Processes data only | `append` (incremental) |
| **Batch 3+** (Remaining files) | `daily` | Processes data only | `append` (incremental) |

### Sample Output

```
🏁 Starting Batch Controller [Env: prod]
🏗️  Deploying Code...
move: s3://trading-pipeline/data/raw/landing/opra-pillar-20250128.cbbo-1m.csv to s3://trading-pipeline/data/raw/staging/opra-pillar-20250128.cbbo-1m.csv
move: s3://trading-pipeline/data/raw/landing/opra-pillar-20250129.cbbo-1m.csv to s3://trading-pipeline/data/raw/staging/opra-pillar-20250129.cbbo-1m.csv
...
🚀 Submitting bootstrap job to EMR Serverless...
⏳ Monitoring Job: 00g387u9hiaj0o0b
✅ Batch Success.
move: s3://trading-pipeline/data/raw/staging/opra-pillar-20250128.cbbo-1m.csv to s3://trading-pipeline/data/raw/processed/opra-pillar-20250128.cbbo-1m.csv
move: s3://trading-pipeline/data/raw/staging/opra-pillar-20250129.cbbo-1m.csv to s3://trading-pipeline/data/raw/processed/opra-pillar-20250129.cbbo-1m.csv
...
🚀 Submitting daily job to EMR Serverless...
⏳ Monitoring Job: 00g3883t57dijo0b
✅ Batch Success.
```

### Pre-Run Checklist (Production)

Before running batch processing in production, ensure clean state:

```bash
# 1. Drop existing tables
aws glue delete-table --database-name "trading_db" --name "bronze_options_chain"
aws glue delete-table --database-name "trading_db" --name "enriched_options_silver"
aws glue delete-table --database-name "trading_db" --name "trading_signals_gold"

# 2. Clean S3 warehouse
aws s3 rm s3://trading-pipeline/iceberg-warehouse/ --recursive

# 3. Verify files are in landing zone
aws s3 ls s3://trading-pipeline/data/raw/landing/

# 4. Run batch controller
./batch_control.sh prod
```

### File Management Commands

```bash
# Move files back to landing (for reprocessing)
aws s3 mv s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline/data/raw/landing/ --recursive

# Clean staging area
aws s3 rm s3://trading-pipeline/data/raw/staging/ --recursive

# Check file counts
aws s3 ls s3://trading-pipeline/data/raw/landing/ | wc -l
aws s3 ls s3://trading-pipeline/data/raw/processed/ | wc -l
```

---

## 🔍 Inspecting Data

### View Table Schema and Sample Data
```bash
uv run python tests/inspect_tables.py

```

This will show:
- Table schema with data types
- Sample rows from the silver table

### Using PySpark Shell (Advanced)
```bash
uv run pyspark
```

Then in the shell:
```python
spark.table("glue_catalog.trading_db.enriched_options_silver").show(5)
spark.table("glue_catalog.trading_db.trading_signals_gold").groupBy("signal").count().show()
```

---

## 📊 Data Schema

### Silver Table Schema

The enriched silver table contains the following columns in order:

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | string | OSI symbol (e.g., "SPX   250221C01000000") |
| `underlying` | string | Mapped tradeable underlying (e.g., "SPY") |
| `trade_date` | date | Date extracted from filename |
| `expiry_date` | date | Option expiration date from symbol |
| `option_type` | string | "CALL" or "PUT" |
| `strike_price` | decimal(10,2) | Strike price (e.g., 1000.00) |
| `ts_recv` | timestamp | Timestamp received |
| `ts_event` | timestamp | Event timestamp |
| `rtype` | integer | Record type |
| `publisher_id` | integer | Publisher ID |
| `instrument_id` | integer | Instrument ID |
| `side` | string | Side (B/A/N) |
| `price` | double | Trade price (if applicable) |
| `size` | integer | Size |
| `flags` | integer | Flags |
| `bid_px_00` | double | Best bid price |
| `ask_px_00` | double | Best ask price |
| `bid_sz_00` | integer | Best bid size |
| `ask_sz_00` | integer | Best ask size |
| `bid_pb_00` | integer | Bid publisher |
| `ask_pb_00` | integer | Ask publisher |
| `mid_price` | decimal(10,2) | Calculated mid price |
| `file_name` | string | Source filename |

### Sample Data

```
+---------------------+----------+----------+-----------+-----------+------------+-------------------+
|symbol               |underlying|trade_date|expiry_date|option_type|strike_price|ts_recv            |
+---------------------+----------+----------+-----------+-----------+------------+-------------------+
|SPX   250221C01000000|SPY       |2025-01-28|2025-02-21 |CALL       |1000.00     |2025-01-28 09:31:00|
+---------------------+----------+----------+-----------+-----------+------------+-------------------+
```

### Gold Table Schema

The gold table contains trading signals:

| Column | Type | Description |
|--------|------|-------------|
| All silver columns | - | Inherited from silver table |
| `signal` | string | Trading signal: "BUY_CALL", "SELL_PUT", or "HOLD" |

### Signal Distribution Example

```
+--------+-------+
|signal  |count  |
+--------+-------+
|HOLD    |940046 |
|SELL_PUT|4535586|
|BUY_CALL|4611298|
+--------+-------+
Total: 10,086,930 records
```

---

## 🐛 Troubleshooting

### Issue: "Java not found"
**Solution:** Install Java 11+ and set `JAVA_HOME`:
```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 11)
```

### Issue: "Module not found" errors
**Solution:** Make sure you're using `uv run`:
```bash
# ❌ Wrong
python src/main.py

# ✅ Correct
uv run python src/main.py
```

### Issue: "Table already exists" error
**Solution:** Run in bootstrap mode to recreate tables:
```bash
uv run python src/main.py --bootstrap
```

### Issue: Version conflicts
**Solution:** Reinstall dependencies:
```bash
uv sync --reinstall
```

### Issue: Permission errors on Mac
**Solution:** Grant terminal full disk access in System Preferences → Security & Privacy

---

## 📊 Pipeline Stages

### 🥉 Bronze Layer (Raw Data)
- Ingests raw CSV files
- Preserves original data

### 🥈 Silver Layer (Enriched Data)
- Adds calculated columns (mid_price, trade_date, expiry_date, option_type from symbol)
- Applies data quality filters (based on YAML config)
- Partitioned by trade_date

### 🥇 Gold Layer (Trading Signals)
- Executes trading strategies
- Generates BUY/SELL/HOLD signals
- Ready for consumption by trading systems

---

## 🔄 Customization

### Adding a New Strategy
1. Create a new file in `src/strategies/` (e.g., `my_strategy.py`)
2. Inherit from `BaseStrategy`
3. Implement `generate_signals()` method
4. Add to `src/strategies/__init__.py`
5. Update `config.yaml` to activate it

### Adding a New Filter
1. Create a new class in `src/filters/bronze_to_silver_filter.py`
2. Inherit from `FilterPolicy`
3. Implement `apply()` method
4. Add to `src/filters/__init__.py`
5. Update `config.yaml` to activate it

---

## 📞 Support

If you encounter any issues:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review the error message carefully
3. Ensure all prerequisites are installed
4. Contact the team for help

---

## 📝 Quick Reference Commands

### Local Development
```bash
# Install dependencies
uv sync

# Run pipeline (first time)
ENV=dev uv run python src/main.py --bootstrap

# Run pipeline (incremental)
ENV=dev uv run python src/main.py

# Inspect tables
uv run python tests/inspect_tables.py

# Check versions
python3 --version
java -version
uv --version
```

### Production (AWS)
```bash
# Batch processing (automated)
./batch_control.sh prod

# Manual single run
bash infrastructure/2_deploy_and_submit.sh bootstrap
bash infrastructure/2_deploy_and_submit.sh daily

# Monitor jobs
bash infrastructure/3_watch_job.sh <job-id>

# Cleanup
bash infrastructure/9_terminate_all.sh
```

### AWS S3 Management
```bash
# Check landing zone
aws s3 ls s3://trading-pipeline/data/raw/landing/

# Move files to landing
aws s3 cp /local/path/*.csv s3://trading-pipeline/data/raw/landing/

# Clean up staging
aws s3 rm s3://trading-pipeline/data/raw/staging/ --recursive

# Archive management
aws s3 ls s3://trading-pipeline/data/raw/processed/
aws s3 mv s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline/data/raw/landing/ --recursive
```

### AWS Glue Table Management
```bash
# Drop tables (for clean restart)
aws glue delete-table --database-name "trading_db" --name "bronze_options_chain"
aws glue delete-table --database-name "trading_db" --name "enriched_options_silver"
aws glue delete-table --database-name "trading_db" --name "trading_signals_gold"

# List tables
aws glue get-tables --database-name "trading_db"

# Clean warehouse
aws s3 rm s3://trading-pipeline/iceberg-warehouse/ --recursive
```

---

**Happy Data Pipelining! 📈**
