#!/bin/bash
# 1_local_strategy_run.sh - Local Dev Strategy Runner
#
# Local equivalent of 1_aws_strategy_run.sh (which submits to AWS EMR).
# Runs strategies locally via PySpark against local Iceberg tables.
#
# Usage:
#   ./1_local_strategy_run.sh                                        # Run all active strategies
#   ./1_local_strategy_run.sh --strategies LaymanSPYStrategy         # Run a specific strategy
#   ./1_local_strategy_run.sh --strategies IronCondorStrategy LaymanSPYStrategy  # Run multiple

set -euo pipefail

echo "🎯 Running strategy locally..."
ENV=dev uv run python src/main.py --mode strategy "$@"
