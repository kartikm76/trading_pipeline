import logging

import strategies
from config import SparkSessionBuilder, ConfigManager
from services.data_load_orchestrator import DataLoadOrchestrator
from services.strategy_orchestrator import StrategyOrchestrator
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_config():
    # Initialize configuration and Spark session
    parser = argparse.ArgumentParser(description='Options Trading Engine')
    parser.add_argument('--mode', choices=['dataload', 'strategy'], required=True)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--strategies', nargs='*', help='Optional list of strategy names')

    args = parser.parse_args()
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()
    return config, spark, args.bootstrap, args.mode, args.strategies

def orchestrate(config, spark, mode, bootstrap_mode, strategy_names=None):
    if mode == 'dataload':
        logger.info(f"🚀 Launching Data Load (Bootstrap: {bootstrap_mode})")
        orchestrator = DataLoadOrchestrator(config, spark)
        orchestrator.run(is_bootstrap=bootstrap_mode)
        return None

    elif mode == 'strategy':
        logger.info("🎯 Launching Strategy SIT")
        orchestrator = StrategyOrchestrator(config, spark)
        return orchestrator.run(strategy_names=strategy_names)

def verify_gold_layer(spark, config, strategy_names=None) -> None:
    """Verify gold tables for each strategy that ran."""
    active_info = config.active_strategy_info
    targets = strategy_names or [s['class'] for s in active_info]

    for name in targets:
        gold_table = f"glue_catalog.{config.db_name}.gold_{name.lower()}"
        try:
            signals = spark.table(gold_table)
            row_count = signals.count()
            logger.info(f"--- Gold Table: {gold_table} ({row_count:,} rows) ---")
            signals.show(10, truncate=False)
        except Exception as e:
            logger.warning(f"Could not read gold table {gold_table}: {e}")

def clean_up(spark) -> None:
    spark.stop()

def main():
    config, spark, bootstrap, mode, strategy_names = initialize_config()
    results = orchestrate(config, spark, mode, bootstrap, strategy_names)

    if mode == 'strategy' and results:
        # Only verify gold tables for strategies that succeeded
        succeeded = [name for name, ok in results.items() if ok]
        if succeeded:
            verify_gold_layer(spark, config, succeeded)

    clean_up(spark)

if __name__ == "__main__":
    logger.info("Starting Pipeline")
    main()
    logger.info("Pipeline Completed")