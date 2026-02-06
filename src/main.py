import logging
from config import SparkSessionBuilder, ConfigManager
from services.orchestrator import PipelineOrchestrator
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_config():
    # Initialize configuration and Spark session
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true")
    args, _ = parser.parse_known_args()

    config = ConfigManager.get_instance()

    spark = SparkSessionBuilder.create()
    return config, spark, args.bootstrap

def orchestrate(config, spark, bootstrap_mode):
    orchestrator = PipelineOrchestrator(config, spark)
    orchestrator.run(is_bootstrap=bootstrap_mode)

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
    config, spark, bootstrap = initialize_config()
    orchestrate(config, spark, bootstrap)
    verify_gold_layer(spark)
    clean_up(spark)

if __name__ == "__main__":
    logger.info("Starting Pipeline")
    main()
    logger.info("Pipeline Completed")