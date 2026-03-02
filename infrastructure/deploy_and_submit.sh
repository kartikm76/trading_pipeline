#!/bin/bash
# infrastructure/deploy_and_submit.sh - Package code, upload to S3, submit EMR job
#
# Usage (Data Loading):
#   ./deploy_and_submit.sh bootstrap   # Submit bootstrap data load job
#   ./deploy_and_submit.sh daily       # Submit daily data load job
#
# Usage (Strategy Execution):
#   ./deploy_and_submit.sh strategy                                    # Daily strategy
#   ./deploy_and_submit.sh strategy --start-date 2025-01-01           # Batch from date
#   ./deploy_and_submit.sh strategy --start-date 2025-01-01 --end-date 2025-02-01  # Batch range
#   ./deploy_and_submit.sh strategy --snapshot                         # Force snapshot mode
#   ./deploy_and_submit.sh strategy --lookback                         # Force lookback mode
#   ./deploy_and_submit.sh strategy --full                             # Force full mode
#
# Note: For Docker image changes, use build_image.sh instead.

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"

source "$SCRIPT_DIR/env_discovery.sh"

# ── Helper ──
get_val() { python3 -c "import yaml; print(yaml.safe_load(open('$PROJECT_ROOT/config.yaml'))$1)"; }

# ── Step 1: Package & Upload Source Code to S3 ──
echo "📦 Packaging source code..."
DIST_DIR="$PROJECT_ROOT/dist"
mkdir -p "$DIST_DIR"
(cd "$PROJECT_ROOT/src" && zip -qr "$DIST_DIR/src.zip" . \
  -x '__pycache__/*' '*/__pycache__/*' '.DS_Store' 'codebase_snapshot.txt')

echo "☁️  Uploading artifacts to S3..."
# Extract S3 bucket from config.yaml based on ENV variable
ENV=${ENV:-aws}
WAREHOUSE=$(get_val "['$ENV']['warehouse']")
S3_BUCKET=$(echo $WAREHOUSE | sed 's|s3://||' | sed 's|/.*||')
echo "   Environment: $ENV | S3 Bucket: $S3_BUCKET"
aws s3 cp "$DIST_DIR/src.zip" "s3://$S3_BUCKET/artifacts/src.zip" --quiet
aws s3 cp "$PROJECT_ROOT/src/main.py" "s3://$S3_BUCKET/artifacts/main.py" --quiet
aws s3 cp "$PROJECT_ROOT/config.yaml" "s3://$S3_BUCKET/artifacts/config.yaml" --quiet
echo "✅ Artifacts uploaded"

# ── Step 2: Determine run type & build argument list ──
RUN_TYPE=${1:-strategy}
shift || true  # Remove first positional arg, keep remaining

PY_ARGS_ARRAY=()
SCALING_KEY="daily"

if [ "$RUN_TYPE" == "bootstrap" ]; then
    PY_ARGS_ARRAY=("--mode" "dataload" "--bootstrap")
    SCALING_KEY="bootstrap"
elif [ "$RUN_TYPE" == "daily" ] && [ "$RUN_TYPE" != "strategy" ]; then
    PY_ARGS_ARRAY=("--mode" "dataload")
    SCALING_KEY="daily"
elif [ "$RUN_TYPE" == "strategy" ]; then
    PY_ARGS_ARRAY=("--mode" "strategy")

    # Parse strategy-specific arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --start-date)
                PY_ARGS_ARRAY+=("--start-date" "$2")
                shift 2
                ;;
            --end-date)
                PY_ARGS_ARRAY+=("--end-date" "$2")
                shift 2
                ;;
            --snapshot)
                PY_ARGS_ARRAY+=("--batch-mode" "snapshot")
                SCALING_KEY="snapshot"
                shift
                ;;
            --lookback)
                PY_ARGS_ARRAY+=("--batch-mode" "lookback")
                SCALING_KEY="lookback"
                shift
                ;;
            --full)
                PY_ARGS_ARRAY+=("--batch-mode" "full")
                SCALING_KEY="full"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
fi

# ── Step 3: Convert array to JSON string for EMR ──
PY_ARGS=""
for i in "${!PY_ARGS_ARRAY[@]}"; do
    if [ $i -gt 0 ]; then
        PY_ARGS="$PY_ARGS, "
    fi
    PY_ARGS="$PY_ARGS\"${PY_ARGS_ARRAY[$i]}\""
done

# ── Step 4: Load scaling & spark config ──
echo "📋 Determining scaling parameters..."
export MAX_EXECS=$(get_val "['scaling']['$SCALING_KEY']['max_executors']")
export EXEC_MEM=$(get_val "['scaling']['$SCALING_KEY']['executor_memory']")
export DRIV_MEM=$(get_val "['scaling']['$SCALING_KEY']['driver_memory']")
source "$SCRIPT_DIR/.spark_config"

# ── Step 5: Submit ──
echo "🚀 Submitting Job:"
echo "   Mode: $RUN_TYPE"
echo "   Scaling: $SCALING_KEY"
echo "   Executors: $MAX_EXECS × $EXEC_MEM"
echo "   Driver: $DRIV_MEM"
echo ""

aws emr-serverless start-job-run \
  --application-id "$APP_ID" \
  --execution-role-arn "$ROLE_ARN" \
  --job-driver "{
    \"sparkSubmit\": {
        \"entryPoint\": \"s3://trading-pipeline/artifacts/main.py\",
        \"entryPointArguments\": [$PY_ARGS],
        \"sparkSubmitParameters\": \"$SUBMIT_PARAMS\"
    }
  }"