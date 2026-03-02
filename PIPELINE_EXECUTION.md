# Pipeline Execution Guide

> **TL;DR:** Most common commands are at the top. Scroll down for parameters and troubleshooting.

---

## 🚀 Most Common Commands

### Daily Tasks (Keep Data Fresh)
```bash
# Load yesterday's data
./infrastructure/deploy_and_submit.sh daily

# Run strategy on new data
./infrastructure/deploy_and_submit.sh strategy
```

### Testing / Single Month
```bash
# Test Jan 2025 only (always use --clear-existing for testing)
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 \
  --end-date 2025-02-01 \
  --clear-existing
```

### Full Year (All 12 Months)
```bash
# Run all months sequentially (~2 hours, $12-15)
./2_yearly_strategy_analysis.sh --year 2025

# Or with parallelism (if you requested AWS quota increase)
./2_yearly_strategy_analysis.sh --year 2025 --max-jobs 4
```

### One-Time Bootstrap
```bash
# Historical data load (only once per refresh)
./infrastructure/deploy_and_submit.sh bootstrap
```

---

## 📊 Data Loading

| Action | Command |
|--------|---------|
| **First-time load** | `./0_aws_pipeline_run.sh` |
| **Daily incremental** | `./infrastructure/deploy_and_submit.sh daily` |
| **Local testing** | `./0_local_pipeline_run.sh` |

---

## 🎯 Strategy Execution

| What You Want | Command |
|---|---|
| **Daily strategy run** | `./infrastructure/deploy_and_submit.sh strategy` |
| **Single month test** | `./infrastructure/deploy_and_submit.sh strategy --start-date 2025-01-01 --end-date 2025-02-01 --clear-existing` |
| **Full year 2025** | `./2_yearly_strategy_analysis.sh --year 2025` |
| **Full year 2024** | `./2_yearly_strategy_analysis.sh --year 2024` |
| **Local test** | `./1_local_strategy_run.sh` |
| **Specific strategy** | `./1_local_strategy_run.sh --strategies LaymanSPYStrategy` |

---

## ⚡ Key Rules (IMPORTANT!)

### Rule 1: `--clear-existing` Usage
- ✅ **Use it** when: Running a single date range for testing
- ❌ **Never use it** when: Running sequential months with `./2_yearly_strategy_analysis.sh`
- Effect: Drops gold table before writing (ensures clean state)

**Example:**
```bash
# ✅ CORRECT - testing single month
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 --end-date 2025-02-01 --clear-existing

# ❌ WRONG - will wipe table after each month
./2_yearly_strategy_analysis.sh --year 2025 --clear-existing
```

### Rule 2: Date Format
- Always use `YYYY-MM-DD` format
- End date is **exclusive** (Jan 31 data needs `--end-date 2025-02-01`)
- Both dates must be provided together

### Rule 3: Batch Modes
- **snapshot** (default) — Monthly batching, no lookback (Iron Condor)
- **lookback** — Sliding windows with historical context (Momentum, IV Percentile)
- **full** — Single large job for entire dataset

Force specific mode:
```bash
./infrastructure/deploy_and_submit.sh strategy --snapshot
./infrastructure/deploy_and_submit.sh strategy --lookback
./infrastructure/deploy_and_submit.sh strategy --full
```

### Rule 4: vCPU Constraints
- Personal AWS has 16 vCPU quota (default)
- = 4 executors × 4 vCPU = only 1 job at a time
- To parallelize: Request AWS quota increase to 64 vCPU, then use `--max-jobs 4`

---

## ✅ Verify Your Results

After running a test, verify the data:

```bash
# Check exact date range in gold table
aws athena start-query-execution \
  --query-string "
    SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
    FROM trading_db.gold_ironcondorstrategy
    WHERE trade_date >= CAST('2025-01-01' AS DATE)
      AND trade_date < CAST('2025-02-01' AS DATE)
  " \
  --query-execution-context Database=trading_db \
  --result-configuration OutputLocation=s3://your-bucket/results/
```

**Expected output for Jan 2025:**
- COUNT: ~252k rows (one day of options data)
- MIN: 2025-01-01
- MAX: 2025-01-31

---

## 📈 Typical Workflow

### Day 1: Initial Setup
```bash
# Bootstrap historical data
./infrastructure/deploy_and_submit.sh bootstrap

# Test Jan 2025 (single month)
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 --end-date 2025-02-01 --clear-existing

# Verify results with SQL query above
```

### Day 2: Full Year
```bash
# Process all 12 months
./2_yearly_strategy_analysis.sh --year 2025

# Wait ~2 hours (sequential) or ~30 min (if parallelism enabled)
```

### Daily: Keep Fresh
```bash
# Every morning
./infrastructure/deploy_and_submit.sh daily
./infrastructure/deploy_and_submit.sh strategy
```

---

## 🐛 Troubleshooting

### Issue: "Type mismatch: date <= varchar"
**Cause:** Gold table has string dates from old run (before date type fix)
**Fix:** Use `--clear-existing` flag to drop and recreate table
```bash
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 --end-date 2025-02-01 --clear-existing
```

### Issue: "No data in results"
**Check:** Is silver table populated for that date range?
```bash
SELECT COUNT(*) FROM trading_db.enriched_options_silver
WHERE trade_date >= '2025-01-01' AND trade_date < '2025-02-01';
```

### Issue: "Job timed out / vCPU exceeded"
**Cause:** Only snapshot mode works on personal AWS (16 vCPU limit)
**Fix:** Use monthly batching:
```bash
./2_yearly_strategy_analysis.sh --year 2025  # Sequential batches
```

### Issue: "Old dates in results when testing"
**Cause:** Forgot `--clear-existing` when running single month test
**Fix:**
```bash
# Drop the table
aws athena start-query-execution \
  --query-string "DROP TABLE trading_db.gold_ironcondorstrategy;" \
  --query-execution-context Database=trading_db \
  --result-configuration OutputLocation=s3://your-bucket/results/

# Rerun with --clear-existing
./infrastructure/deploy_and_submit.sh strategy \
  --start-date 2025-01-01 --end-date 2025-02-01 --clear-existing
```

### Issue: "Module not found (local dev)"
**Cause:** Running without `uv`
**Fix:** Use `uv run`:
```bash
# ✅ CORRECT
uv run python src/main.py --mode strategy

# ❌ WRONG
python src/main.py --mode strategy
```

### Issue: "Java not found"
**Fix:**
```bash
brew install openjdk@11
export JAVA_HOME=$(/usr/libexec/java_home -v 11)
```

---

## 📊 Expected Runtime & Cost

| Scenario | Time | Cost | Notes |
|----------|------|------|-------|
| 1 day | ~5-10 min | $1 | Single trade_date |
| 1 month | ~10 min | $2 | ~252k trades |
| Full year (sequential) | ~2 hours | $12-15 | ✅ Works with 16 vCPU |
| Full year (4 parallel) | ~30 min | $12-15 | Needs 64 vCPU quota |

**Note:** Cost is the same regardless of execution speed—you only pay for compute time used.

---

## 🔍 Monitoring Jobs

```bash
# Watch a job (polls every 10s)
./infrastructure/watch_job.sh <job-run-id>

# Check status
aws emr-serverless get-job-run \
  --application-id $(cat .application-id) \
  --job-run-id <job-run-id> \
  --query 'jobRun.{state:state,details:stateDetails}'

# View Spark UI
aws emr-serverless get-dashboard-for-job-run \
  --application-id $(cat .application-id) \
  --job-run-id <job-run-id> --query 'url' --output text
```

---

## 🎓 Understanding Batch Modes

| Mode | Use Case | Batching | Output |
|------|----------|----------|--------|
| **snapshot** | Iron Condor (single date decisions) | Monthly | Non-overlapping (one trade_date each) |
| **lookback** | Momentum, IV Percentile (need history) | Sliding windows | Filtered to avoid duplicates |
| **full** | Correlation, position tracking | One large job | Complete dataset |

For personal AWS (16 vCPU), **only snapshot mode is practical**.

---

## 🆘 Need More Help?

- **Architecture overview?** → See README.md → "Architecture" section
- **Adding a new strategy?** → See README.md → "Adding a New Strategy" section
- **Configuration details?** → See README.md → "Configuration" section
- **Project structure?** → See README.md → "Project Structure" section
