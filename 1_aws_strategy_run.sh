#!/bin/bash
# 1_aws_strategy_run.sh - AWS Strategy Runner (Approach 1: S3-based)
#
# Approach 1 workflow:
#   - Source code is zipped & uploaded to S3 (fast, ~seconds)
#   - Docker image is ONLY for pip dependencies (rebuild only when deps change)
#   - deploy_and_submit.sh handles: zip → S3 upload → EMR job submit
#
# Usage:
#   ./1_aws_strategy_run.sh                    # Run all active strategies
#   ./1_aws_strategy_run.sh --strategies IronCondorStrategy IronButterflyStrategy

# Pass all arguments through (e.g., --strategies)
./infrastructure/deploy_and_submit.sh "strategy" "$@"