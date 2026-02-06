# Trading Pipeline - Options Chain Data Processing

A production-ready data pipeline for processing options chain data using PySpark, Apache Iceberg, and the Medallion Architecture (Bronze → Silver → Gold).

## 📋 Table of Contents
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Running the Pipeline](#-running-the-pipeline)
  - [Local Run](#-local-run)
  - [Production Run (AWS EMR Serverless)](#-production-run-aws-emr-serverless)
- [Inspecting Data](#-inspecting-data)
- [Data Schema](#-data-schema)
- [Quick Reference Commands](#-quick-reference-commands)
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

### config.yaml
This file controls all pipeline settings. Key sections:

```yaml
project:
  name: "Option Trading Pipeline"

storage:
  catalog_name: "glue_catalog"
  db_name: "trading_db"
  tables:
    bronze: "bronze_options_chain"
    silver: "enriched_options_silver"
    gold: "strategy_signals"

data_format:
  raw: "csv"           # Format of input data
  iceberg: "parquet"   # Format for Iceberg tables

dev:
  catalog_type: "hadoop"
  use_location_clause: false
  raw_base_path: "./data/raw"              # Local directory
  warehouse: "./iceberg-warehouse/"

prod:
  catalog_impl: "org.apache.iceberg.aws.glue.GlueCatalog"
  io_impl: "org.apache.iceberg.aws.s3.S3FileIO"
  use_location_clause: true
  raw_base_path: "s3://trading-pipeline/data/raw"  # S3 bucket
  warehouse: "s3://trading-pipeline/iceberg-warehouse/"

strategies:
  - class: "LaymanSPYStrategy"
    active: "Y"
    underlying: "SPY"

filters:
  - class: "ZeroDTEPolicy"
    active: "N"
  - class: "LiquidityPolicy"
    active: "N"

underlying_mapping:
  SPX: "SPY"   # S&P 500 Index → SPDR S&P 500 ETF
  NDX: "QQQ"   # Nasdaq-100 Index → Invesco QQQ ETF
  RUT: "IWM"   # Russell 2000 Index → iShares Russell 2000 ETF
```

---

## 🚀 Running the Pipeline

The pipeline can run in two environments: **Local** (for development/testing) and **Production** (AWS EMR Serverless).

---

## 💻 Local Run

### Prerequisites
- Place your CSV files in `./data/raw/` directory
- Ensure local directories exist

### Setup Data Directory
```bash
mkdir -p data/raw
# Copy your CSV file(s) here
cp /path/to/your/opra-pillar-*.csv data/raw/
```

### Bootstrap Mode (First Time)
Creates all tables from scratch:

```bash
ENV=dev uv run python src/main.py --bootstrap
```

**What happens:**
1. ✅ Creates local Iceberg catalog (Hadoop-based)
2. ✅ Reads CSV from `./data/raw/` directory
3. ✅ Creates Bronze table with raw data
4. ✅ Creates Silver table with enriched data
5. ✅ Creates Gold table with trading signals
6. ✅ Stores tables in `./iceberg-warehouse/`

**Expected Output:**
```
Setting up Iceberg infrastructure...
Creating catalog: glue_catalog
Creating database: trading_db
Ingesting data from CSV...
Processing 10M+ records...
--- [Orchestration] Gold table glue_catalog.trading_db.strategy_signals created ---
```

### Daily Mode (Incremental)
Appends new data without recreating tables:

```bash
ENV=dev 
uv run python src/main.py
```

**What happens:**
1. ✅ Reads new CSV files from `./data/raw/`
2. ✅ Appends to existing Bronze table
3. ✅ Appends to existing Silver table (decomposed OSI symbols + any active filters)
4. ✅ Appends to existing Gold table (strategy signals)

### Inspect Local Tables
```bash
uv run python tests/inspect_tables.py
```

**Output shows:**
- Table schemas with data types
- Sample rows from each table
- Record counts

---

## ☁️ Production Run (AWS EMR Serverless)

### Prerequisites
- AWS EMR Serverless application configured
- IAM roles set up (use `infrastructure/1_setup_iam_role.sh`)
- S3 bucket: `s3://trading-pipeline/`
- CSV files uploaded to S3 landing zone

### Data Flow Architecture

**S3 Landing → S3 Staging → Spark Processing → S3 Processed (Archive)**

```
s3://trading-pipeline/data/raw/
├── landing/          # Upload CSV files here
├── staging/          # Files being processed (temporary)
└── processed/        # Successfully processed files (archive)
```

### Pre-Run Checklist

Before running production pipeline, ensure clean state:

```bash
# 1. Drop existing Glue tables
aws glue delete-table --database-name "trading_db" --name "bronze_options_chain"
aws glue delete-table --database-name "trading_db" --name "enriched_options_silver"
aws glue delete-table --database-name "trading_db" --name "strategy_signals"

# 2. Clean S3 Iceberg warehouse
aws s3 rm s3://trading-pipeline/iceberg-warehouse/ --recursive

# 3. Upload CSV files to landing zone
aws s3 cp /local/path/*.csv s3://trading-pipeline/data/raw/landing/

# 4. Verify files are in landing
aws s3 ls s3://trading-pipeline/data/raw/landing/
```

### Option 1: Automated Batch Processing (Recommended)

Use `batch_control.sh` for bulk file processing:

```bash
./batch_control.sh prod
```

**How it works:**
1. **Batch 1** (First 15 files): Runs in `bootstrap` mode → Creates tables
2. **Batch 2+** (Next 15 files each): Runs in `daily` mode → Appends data
3. Files move: `landing/` → `staging/` → `processed/`

**Sample Output:**
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
...
🚀 Submitting daily job to EMR Serverless...
⏳ Monitoring Job: 00g3883t57dijo0b
✅ Batch Success.
```

### Option 2: Manual Single Run

For manual control over individual runs:

#### Bootstrap Mode (First Time)
```bash
bash infrastructure/2_deploy_and_submit.sh bootstrap
```

**What happens:**
1. ✅ Packages code and uploads to S3
2. ✅ Submits Spark job to EMR Serverless
3. ✅ Reads CSV from `s3://trading-pipeline/data/raw/staging/`
4. ✅ Creates Bronze, Silver, Gold tables in AWS Glue Catalog
5. ✅ Stores Iceberg data in `s3://trading-pipeline/iceberg-warehouse/`

#### Daily Mode (Incremental)
```bash
bash infrastructure/2_deploy_and_submit.sh daily
```

**What happens:**
1. ✅ Submits Spark job (no code upload needed)
2. ✅ Reads new CSV files from staging
3. ✅ Appends to existing tables

#### Monitor Job
```bash
bash infrastructure/3_watch_job.sh <job-id>
```

### S3 File Management

```bash
# Check file counts
aws s3 ls s3://trading-pipeline/data/raw/landing/ | wc -l
aws s3 ls s3://trading-pipeline/data/raw/staging/ | wc -l
aws s3 ls s3://trading-pipeline/data/raw/processed/ | wc -l

# Move files between directories
aws s3 mv s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline/data/raw/landing/ --recursive

# Clean staging area
aws s3 rm s3://trading-pipeline/data/raw/staging/ --recursive

# Upload new files
aws s3 cp /local/path/*.csv s3://trading-pipeline/data/raw/landing/
```

### Workflow Phases (Batch Processing)

| Phase | Mode | Action | Table Operation |
|-------|------|--------|-----------------|
| **Batch 1** (First 15 files) | `bootstrap` | Deploy code + process data | `createOrReplace` (clean start) |
| **Batch 2** (Next 15 files) | `daily` | Process data only | `append` (incremental) |
| **Batch 3+** (Remaining files) | `daily` | Process data only | `append` (incremental) |

### Cleanup

```bash
# Terminate all EMR resources
bash infrastructure/9_terminate_all.sh
```

---

## 🔍 Inspecting Data

### Local Environment

View table schemas and sample data:

```bash
uv run python tests/inspect_tables.py

```

**Output shows:**
- Table schemas with data types
- Sample rows from Bronze, Silver, and Gold tables
- Record counts

### Using PySpark Shell (Advanced)
```bash
uv run pyspark
```

Then in the shell:
```python
# View silver table
spark.table("glue_catalog.trading_db.enriched_options_silver").show(5)

# View gold table with signal distribution
spark.table("glue_catalog.trading_db.strategy_signals").groupBy("signal").count().show()
```

### Production Environment (AWS)

Query tables using AWS Athena or EMR Studio:

```sql
-- View silver table
SELECT * FROM glue_catalog.trading_db.enriched_options_silver LIMIT 10;

-- Signal distribution
SELECT signal, COUNT(*) as count
FROM glue_catalog.trading_db.strategy_signals
GROUP BY signal;

-- Daily summary
SELECT trade_date, underlying, COUNT(*) as records
FROM glue_catalog.trading_db.enriched_options_silver
GROUP BY trade_date, underlying
ORDER BY trade_date DESC;
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

### 💻 Local Development

```bash
# Install dependencies
uv sync

# Bootstrap mode (first time - creates tables)
ENV=dev uv run python src/main.py --bootstrap

# Daily mode (incremental - appends data)
ENV=dev uv run python src/main.py

# Inspect tables
uv run python tests/inspect_tables.py

# Check versions
python3 --version
java -version
uv --version
```

### ☁️ Production (AWS EMR Serverless)

#### Automated Batch Processing
```bash
# Process all files in landing zone (recommended)
./batch_control.sh prod
```

#### Manual Single Run
```bash
# Bootstrap mode (first time - creates tables)
bash infrastructure/2_deploy_and_submit.sh bootstrap

# Daily mode (incremental - appends data)
bash infrastructure/2_deploy_and_submit.sh daily

# Monitor running job
bash infrastructure/3_watch_job.sh <job-id>

# Cleanup all resources
bash infrastructure/9_terminate_all.sh
```

#### S3 File Management
```bash
# Upload files to landing zone
aws s3 cp /local/path/*.csv s3://trading-pipeline/data/raw/landing/

# Check file counts
aws s3 ls s3://trading-pipeline/data/raw/landing/ | wc -l
aws s3 ls s3://trading-pipeline/data/raw/staging/ | wc -l
aws s3 ls s3://trading-pipeline/data/raw/processed/ | wc -l

# Move processed files back to landing (for reprocessing)
aws s3 mv s3://trading-pipeline/data/raw/processed/ s3://trading-pipeline/data/raw/landing/ --recursive

# Clean staging area
aws s3 rm s3://trading-pipeline/data/raw/staging/ --recursive
```

#### AWS Glue Table Management
```bash
# Drop tables (for clean restart)
aws glue delete-table --database-name "trading_db" --name "bronze_options_chain"
aws glue delete-table --database-name "trading_db" --name "enriched_options_silver"
aws glue delete-table --database-name "trading_db" --name "strategy_signals"

# List all tables
aws glue get-tables --database-name "trading_db"

# Clean Iceberg warehouse
aws s3 rm s3://trading-pipeline/iceberg-warehouse/ --recursive
```

---

**Happy Data Pipelining! 📈**
