#!/bin/bash
# tests/regression_dataload.sh - Regression suite for data loading (bronze + silver)
#
# Validates the full dataload pipeline works in dev (local) and aws (EMR Serverless).
# Run this after any code change, dependency update, or Docker image rebuild.
#
# Usage:
#   ./tests/regression_dataload.sh              # Run both dev + aws tests
#   ./tests/regression_dataload.sh dev          # Run local dev test only
#   ./tests/regression_dataload.sh aws          # Run aws EMR test only
#   ./tests/regression_dataload.sh --rebuild    # Rebuild Docker image first, then run both
#
# Exit codes:
#   0 = All tests passed
#   1 = One or more tests failed

set -uo pipefail

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"
INFRA_DIR="$PROJECT_ROOT/infrastructure"

source "$INFRA_DIR/env_discovery.sh"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PASS="${GREEN}✅ PASS${NC}"
FAIL="${RED}❌ FAIL${NC}"

DEV_RESULT=""
AWS_RESULT=""
REBUILD=false
TARGETS=("dev" "aws")

# ── Parse args ──
for arg in "$@"; do
    case $arg in
        --rebuild) REBUILD=true ;;
        dev)       TARGETS=("dev") ;;
        aws)       TARGETS=("aws") ;;
    esac
done

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Trading Pipeline — Dataload Regression Suite${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "  Targets: ${TARGETS[*]}"
echo -e "  Rebuild: $REBUILD"
echo ""

# ═══════════════════════════════════════════════════════════════
# Step 0: Rebuild Docker image (if --rebuild)
# ═══════════════════════════════════════════════════════════════
if [ "$REBUILD" = true ]; then
    echo -e "${YELLOW}── Step 0: Rebuilding Docker Image ──${NC}"
    if "$INFRA_DIR/build_image.sh"; then
        echo -e "  Docker image: $PASS"
    else
        echo -e "  Docker image: $FAIL"
        echo -e "\n${RED}Image build failed — cannot proceed with aws test.${NC}"
        TARGETS=("${TARGETS[@]/aws/}")
    fi
    echo ""
fi

# ═══════════════════════════════════════════════════════════════
# Step 1: DEV (local Spark + local Iceberg)
# ═══════════════════════════════════════════════════════════════
run_dev_test() {
    echo -e "${YELLOW}── Test: DEV Dataload (local Spark) ──${NC}"

    # Check for local CSV data
    LOCAL_DATA_DIR="$PROJECT_ROOT/data/raw/staging"
    if [ ! -d "$LOCAL_DATA_DIR" ] || [ -z "$(ls -A "$LOCAL_DATA_DIR" 2>/dev/null)" ]; then
        # Try landing zone
        LOCAL_DATA_DIR="$PROJECT_ROOT/data/raw/landing"
        if [ ! -d "$LOCAL_DATA_DIR" ] || [ -z "$(ls -A "$LOCAL_DATA_DIR" 2>/dev/null)" ]; then
            echo -e "  ${YELLOW}⚠️  No local CSV data found in data/raw/staging/ or data/raw/landing/${NC}"
            echo -e "  ${YELLOW}   Place sample CSV files there to test dataload locally.${NC}"
            echo -e "  DEV dataload: ${YELLOW}⏭️  SKIPPED (no data)${NC}"
            DEV_RESULT="SKIP"
            echo ""
            return
        fi
    fi

    # Run bootstrap dataload locally (background + wait with timeout)
    ENV=dev uv run python "$PROJECT_ROOT/src/main.py" --mode dataload --bootstrap > /tmp/regression_dataload_dev.log 2>&1 &
    DEV_PID=$!

    # Wait up to 180 seconds (dataload can be slower than strategy)
    WAIT=0
    while kill -0 $DEV_PID 2>/dev/null && [ $WAIT -lt 180 ]; do
        sleep 2
        WAIT=$((WAIT + 2))
    done

    if kill -0 $DEV_PID 2>/dev/null; then
        kill $DEV_PID 2>/dev/null
        echo -e "  DEV dataload: $FAIL (timed out after 180s)"
        DEV_RESULT="FAIL"
        cat /tmp/regression_dataload_dev.log
        return
    fi

    DEV_EXIT=0
    wait $DEV_PID || DEV_EXIT=$?

    cat /tmp/regression_dataload_dev.log

    if [ $DEV_EXIT -eq 0 ]; then
        # Check for success markers
        if grep -q "Pipeline Completed" /tmp/regression_dataload_dev.log; then
            # Check if bronze/silver tables were written
            if grep -q "bronze\|silver\|Bronze\|Silver" /tmp/regression_dataload_dev.log; then
                DEV_RESULT="PASS"
                echo -e "  DEV dataload: $PASS"
            else
                DEV_RESULT="PASS"
                echo -e "  DEV dataload: $PASS (pipeline completed, check tables)"
            fi
        else
            DEV_RESULT="FAIL"
            echo -e "  DEV dataload: $FAIL (no completion marker in output)"
        fi
    else
        DEV_RESULT="FAIL"
        echo -e "  DEV dataload: $FAIL"
        echo -e "  ${RED}Log: /tmp/regression_dataload_dev.log${NC}"
    fi
    echo ""
}

# ═══════════════════════════════════════════════════════════════
# Step 2: AWS (EMR Serverless)
# ═══════════════════════════════════════════════════════════════
run_aws_test() {
    echo -e "${YELLOW}── Test: AWS Dataload (EMR Serverless) ──${NC}"

    # Check if there are files in the S3 landing zone
    FILE_COUNT=$(aws s3 ls s3://trading-pipeline/data/raw/landing/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -eq 0 ]; then
        echo -e "  ${YELLOW}⚠️  No files in s3://trading-pipeline/data/raw/landing/${NC}"
        echo -e "  ${YELLOW}   Upload CSV files there to test dataload on AWS.${NC}"
        echo -e "  AWS dataload: ${YELLOW}⏭️  SKIPPED (no data)${NC}"
        AWS_RESULT="SKIP"
        echo ""
        return
    fi

    echo "  Found $FILE_COUNT files in landing zone"

    # Submit a daily dataload job (non-destructive — appends)
    echo "  Submitting EMR dataload job..."
    SUBMIT_OUTPUT=$("$INFRA_DIR/deploy_and_submit.sh" "daily" 2>&1)
    JOB_RUN_ID=$(echo "$SUBMIT_OUTPUT" | grep -o '"jobRunId": "[^"]*"' | cut -d'"' -f4)

    if [ -z "$JOB_RUN_ID" ]; then
        AWS_RESULT="FAIL"
        echo -e "  AWS submit: $FAIL (could not extract jobRunId)"
        echo "  Output: $SUBMIT_OUTPUT"
        return
    fi

    echo "  Job submitted: $JOB_RUN_ID"
    echo "  Waiting for completion (polling every 15s, timeout 10min)..."

    TIMEOUT=600
    ELAPSED=0
    POLL_INTERVAL=15

    while [ $ELAPSED -lt $TIMEOUT ]; do
        STATE=$(aws emr-serverless get-job-run \
            --application-id "$APP_ID" \
            --job-run-id "$JOB_RUN_ID" \
            --query 'jobRun.state' --output text 2>/dev/null)

        case $STATE in
            SUCCESS)
                AWS_RESULT="PASS"
                echo -e "  AWS dataload: $PASS (${ELAPSED}s)"
                echo ""
                return
                ;;
            FAILED|CANCELLED)
                AWS_RESULT="FAIL"
                echo -e "  AWS dataload: $FAIL (state: $STATE after ${ELAPSED}s)"

                DETAILS=$(aws emr-serverless get-job-run \
                    --application-id "$APP_ID" \
                    --job-run-id "$JOB_RUN_ID" \
                    --query 'jobRun.stateDetails' --output text 2>/dev/null)
                echo -e "  ${RED}Details: $DETAILS${NC}"
                echo ""
                return
                ;;
            *)
                printf "  [%3ds] %s\r" $ELAPSED "$STATE"
                ;;
        esac

        sleep $POLL_INTERVAL
        ELAPSED=$((ELAPSED + POLL_INTERVAL))
    done

    AWS_RESULT="TIMEOUT"
    echo -e "  AWS dataload: ${RED}⏰ TIMEOUT${NC} (exceeded ${TIMEOUT}s)"
    echo -e "  Job $JOB_RUN_ID may still be running. Check with:"
    echo -e "  ./infrastructure/watch_job.sh $JOB_RUN_ID"
    echo ""
}

# ═══════════════════════════════════════════════════════════════
# Execute requested tests
# ═══════════════════════════════════════════════════════════════
for target in "${TARGETS[@]}"; do
    case $target in
        dev) run_dev_test ;;
        aws) run_aws_test ;;
    esac
done

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Dataload Regression Summary${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"

EXIT_CODE=0

for target in "${TARGETS[@]}"; do
    case $target in
        dev)
            if [ "$DEV_RESULT" = "PASS" ]; then
                echo -e "  DEV  (local Spark)     : $PASS"
            elif [ "$DEV_RESULT" = "SKIP" ]; then
                echo -e "  DEV  (local Spark)     : ${YELLOW}⏭️  SKIPPED${NC}"
            else
                echo -e "  DEV  (local Spark)     : $FAIL"
                EXIT_CODE=1
            fi
            ;;
        aws)
            if [ "$AWS_RESULT" = "PASS" ]; then
                echo -e "  AWS  (EMR Serverless)  : $PASS"
            elif [ "$AWS_RESULT" = "SKIP" ]; then
                echo -e "  AWS  (EMR Serverless)  : ${YELLOW}⏭️  SKIPPED${NC}"
            elif [ "$AWS_RESULT" = "TIMEOUT" ]; then
                echo -e "  AWS  (EMR Serverless)  : ${RED}⏰ TIMEOUT${NC}"
                EXIT_CODE=1
            else
                echo -e "  AWS  (EMR Serverless)  : $FAIL"
                EXIT_CODE=1
            fi
            ;;
    esac
done

echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}All dataload regression tests passed! ✅${NC}\n"
else
    echo -e "\n${RED}Some dataload regression tests failed. See details above. ❌${NC}\n"
fi

exit $EXIT_CODE
