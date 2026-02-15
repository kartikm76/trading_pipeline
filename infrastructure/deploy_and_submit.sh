#!/bin/bash
# infrastructure/2_deploy_and_submit.sh - The Logic Translator

source "$(dirname "$0")/env_discovery.sh"

# Accepts: bootstrap, daily, or strategy
RUN_TYPE=${1:-strategy}
get_val() { python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))$1)"; }

# MAP RUN_TYPE TO PROPERLY QUOTED JSON ARGUMENTS
if [ "$RUN_TYPE" == "bootstrap" ]; then
    PY_ARGS="\"--mode\", \"dataload\", \"--bootstrap\""
    SCALING_KEY="bootstrap"
elif [ "$RUN_TYPE" == "daily" ]; then
    PY_ARGS="\"--mode\", \"dataload\""
    SCALING_KEY="daily"
else
    # Default to Strategy SIT
    PY_ARGS="\"--mode\", \"strategy\""
    SCALING_KEY="daily"
fi

# Load Scaling and Spark Config
export MAX_EXECS=$(get_val "['scaling']['$SCALING_KEY']['max_executors']")
export EXEC_MEM=$(get_val "['scaling']['$SCALING_KEY']['executor_memory']")
export DRIV_MEM=$(get_val "['scaling']['$SCALING_KEY']['driver_memory']")
source "$(dirname "$0")/.spark_config"

echo "🚀 Submitting Job: Mode=[$RUN_TYPE] | Scaling=[$SCALING_KEY]"

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