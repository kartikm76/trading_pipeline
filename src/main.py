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

def orchestrate(config, spark, mode, bootstrap_mode):
    if mode == 'dataload':
        orchestrator = DataLoadOrchestrator(config, spark)
        orchestrator.run(is_bootstrap=bootstrap_mode)

    elif mode == 'strategy':
        orchestrator = StrategyOrchestrator(config, spark)
        orchestrator.run(strategy_names=strategies)

def verify_gold_layer(spark) -> None:
    # Check the final Gold signals
    signals = spark.table("glue_catalog.trading_db.strategy_signals")
    logger.info("--- Sample Trading Signals ---")
    signals.select("symbol", "mid_price", "signal").filter("signal != 'HOLD'").show(10)

    # Verify the distribution of signals
    logger.info("--- Signal Distribution ---")
    signals.groupBy("signal").count().show()

def clean_up(spark) -> None:
    spark.stop()

def main():
    config, spark, bootstrap, mode, strategies = initialize_config()
    orchestrate(config, spark, mode, bootstrap)
    verify_gold_layer(spark)
    clean_up(spark)

if __name__ == "__main__":
    logger.info("Starting Pipeline")
    main()
    logger.info("Pipeline Completed")