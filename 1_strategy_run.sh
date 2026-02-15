#!/bin/bash
# 1_strategy_run.sh - Strategy 2: SIT On-Demand Testing

# 1. Build image with latest strategy edits
./infrastructure/build_image.sh

# 2. Run in strategy mode
./infrastructure/deploy_and_submit.sh "strategy"