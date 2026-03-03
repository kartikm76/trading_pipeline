#!/bin/bash
# 2_yearly_strategy_analysis.sh - Run full-year strategy analysis with monthly batching
#
# Executes snapshot strategies (e.g., iron condor) on entire 2025 dataset
# using monthly batching approach: 12 parallel jobs × ~200M rows each
#
# Usage:
#   ./2_yearly_strategy_analysis.sh [OPTIONS]
#
# OPTIONS:
#   --year YYYY              Year to analyze (default: 2025)
#   --snapshot               Force snapshot mode only
#   --lookback               Force lookback mode only
#   --full                   Force full mode only
#   --max-jobs N             Max parallel jobs (default: 1, due to AWS vCPU limits)
#
# Examples:
#   ./2_yearly_strategy_analysis.sh                                   # Default: 2025, all modes, sequential
#   ./2_yearly_strategy_analysis.sh --year 2024                       # Run 2024 data
#   ./2_yearly_strategy_analysis.sh --year 2025 --snapshot            # 2025 in snapshot mode
#   ./2_yearly_strategy_analysis.sh --snapshot --max-jobs 2           # Snapshot mode, 2 parallel jobs
#   ./2_yearly_strategy_analysis.sh --year 2024 --snapshot --max-jobs 4  # All combined!

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (with defaults)
YEAR="2025"
MODE=""
MAX_PARALLEL_JOBS="1"  # Default: sequential (due to AWS vCPU limits)

# Parse command-line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --year)
                YEAR="$2"
                shift 2
                ;;
            --snapshot)
                MODE="--snapshot"
                shift
                ;;
            --lookback)
                MODE="--lookback"
                shift
                ;;
            --full)
                MODE="--full"
                shift
                ;;
            --max-jobs)
                MAX_PARALLEL_JOBS="$2"
                shift 2
                ;;
            *)
                echo "Unknown option: $1"
                shift
                ;;
        esac
    done
}

# Parse arguments first
parse_args "$@"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="$SCRIPT_DIR/infrastructure/deploy_and_submit.sh"
LOG_DIR="$SCRIPT_DIR/logs/yearly_analysis"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/yearly_analysis_${YEAR}_${TIMESTAMP}.log"

# Ensure deploy script exists
if [ ! -f "$DEPLOY_SCRIPT" ]; then
    echo -e "${RED}❌ Error: $DEPLOY_SCRIPT not found${NC}"
    exit 1
fi

# Create log directory
mkdir -p "$LOG_DIR"

# Generate monthly batches for given year
generate_batches() {
    local year=$1
    local months=(01 02 03 04 05 06 07 08 09 10 11 12)

    for month in "${months[@]}"; do
        local start_date="${year}-${month}-01"
        local next_month=$(printf "%02d" $((10#$month + 1)))
        local next_year=$year

        if [ "$next_month" -gt 12 ]; then
            next_month="01"
            next_year=$((year + 1))
        fi

        local end_date="${next_year}-${next_month}-01"
        echo "$start_date:$end_date"
    done
}

# Execute a single batch
execute_batch() {
    local batch_num=$1
    local start_date=$2
    local end_date=$3
    local mode=$4

    echo -e "${BLUE}[Batch $batch_num] 📦 Starting: $start_date to $end_date${NC}" | tee -a "$LOG_FILE"

    # Call deploy_and_submit.sh with batch parameters
    if [ -n "$mode" ]; then
        "$DEPLOY_SCRIPT" "strategy" \
            --start-date "$start_date" \
            --end-date "$end_date" \
            $mode \
            >> "$LOG_FILE" 2>&1
    else
        "$DEPLOY_SCRIPT" "strategy" \
            --start-date "$start_date" \
            --end-date "$end_date" \
            >> "$LOG_FILE" 2>&1
    fi

    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}[Batch $batch_num] ✅ Completed${NC}" | tee -a "$LOG_FILE"
    else
        echo -e "${RED}[Batch $batch_num] ❌ Failed (exit code: $exit_code)${NC}" | tee -a "$LOG_FILE"
    fi

    return $exit_code
}

# Main execution
main() {
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}🚀 Yearly Strategy Analysis - Full Year Dataset${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""

    # AWS vCPU Warning
    echo -e "${YELLOW}⚠️  AWS EMR Serverless vCPU Limits:${NC}"
    echo "   Your account quota: 16 vCPU (default for personal accounts)"
    echo "   Per job (snapshot): 4 executors × 4 vCPU = 16 vCPU"
    echo "   Max safe parallelism: 1 job at a time"
    echo ""

    if [ "$MAX_PARALLEL_JOBS" -gt 1 ]; then
        echo -e "${YELLOW}⚠️  WARNING: You requested $MAX_PARALLEL_JOBS parallel jobs!${NC}"
        echo "   This exceeds your 16 vCPU quota."
        echo "   Additional jobs will queue or fail."
        echo ""
        echo "   Options:"
        echo "   1. Run sequentially (--max-jobs 1)     → 2 hours, safer"
        echo "   2. Request quota increase on AWS       → faster parallel"
        echo "   3. Reduce executors in config.yaml     → slower but works"
        echo ""
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Cancelled."
            return 1
        fi
    fi

    echo "📊 Configuration:"
    echo "   Year: $YEAR"
    echo "   Mode: ${MODE:-all modes}"
    echo "   Max Parallel Jobs: $MAX_PARALLEL_JOBS"
    echo "   Total Time (est): $((12 * 10 / $MAX_PARALLEL_JOBS)) minutes"
    echo "   Log File: $LOG_FILE"
    echo ""

    # Generate batches
    mapfile -t batches < <(generate_batches "$YEAR")
    total_batches=${#batches[@]}

    echo -e "${BLUE}📦 Generated $total_batches monthly batches${NC}"
    echo ""

    # Track job pids and batch info
    declare -A batch_pids
    declare -A batch_info
    active_jobs=0
    completed_jobs=0
    failed_jobs=0

    # Submit batches with concurrency control
    for batch_num in $(seq 1 $total_batches); do
        batch_idx=$((batch_num - 1))
        IFS=':' read -r start_date end_date <<< "${batches[$batch_idx]}"

        # Wait if we've reached max parallel jobs
        while [ $active_jobs -ge $MAX_PARALLEL_JOBS ]; do
            # Check for completed jobs
            for pid in "${!batch_pids[@]}"; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    # Job finished, check result
                    wait "$pid"
                    local result=$?
                    local batch_info_str="${batch_pids[$pid]}"

                    if [ $result -eq 0 ]; then
                        ((completed_jobs++))
                    else
                        ((failed_jobs++))
                    fi

                    unset batch_pids[$pid]
                    ((active_jobs--))
                fi
            done
            sleep 2
        done

        # Submit batch
        execute_batch "$batch_num" "$start_date" "$end_date" "$MODE" &
        local pid=$!
        batch_pids[$pid]="$batch_num:$start_date:$end_date"
        ((active_jobs++))

        echo -e "${YELLOW}[Progress] Jobs running: $active_jobs / completed: $completed_jobs / failed: $failed_jobs${NC}"
    done

    # Wait for all remaining jobs
    echo ""
    echo -e "${BLUE}⏳ Waiting for all batches to complete...${NC}"

    for pid in "${!batch_pids[@]}"; do
        wait "$pid"
        local result=$?

        if [ $result -eq 0 ]; then
            ((completed_jobs++))
        else
            ((failed_jobs++))
        fi

        ((active_jobs--))
        echo -e "${YELLOW}[Progress] Completed: $completed_jobs / Failed: $failed_jobs / Running: $active_jobs${NC}"
    done

    # Final summary
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}📊 Analysis Complete${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo "Total Batches: $total_batches"
    echo -e "Completed: ${GREEN}$completed_jobs${NC}"
    echo -e "Failed: $([ $failed_jobs -eq 0 ] && echo -e "${GREEN}$failed_jobs${NC}" || echo -e "${RED}$failed_jobs${NC}")"
    echo ""
    echo "📝 Full log: $LOG_FILE"
    echo ""

    if [ $failed_jobs -eq 0 ]; then
        echo -e "${GREEN}✅ All batches completed successfully!${NC}"
        echo ""
        echo "📋 Next Steps:"
        echo "   1. Verify gold table: gold_ironcondorstrategy"
        echo "   2. Query results:"
        echo "      spark-sql> SELECT COUNT(*), COUNT(DISTINCT trade_date) FROM gold_ironcondorstrategy;"
        echo "      spark-sql> SELECT * FROM gold_ironcondorstrategy LIMIT 10;"
        echo ""
        return 0
    else
        echo -e "${RED}❌ Some batches failed. Check log for details.${NC}"
        return 1
    fi
}

# Execute
main "$@"
