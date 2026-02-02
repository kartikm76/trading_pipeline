from adapters.adapter_factory import AdapterFactory
from strategies.layman_spy_strategy import LaymanSPYStrategy
from config import SparkSessionBuilder, ConfigManager
from utils.iceberg_setup import IcebergTableManager
from pyspark.sql import functions as F
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def initialize_config():
    # --- 0. CAPTURE FLAGS ---
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true", help="Run initial 200GB load")
    args, unknown = parser.parse_known_args()
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()
    return config, spark, args.bootstrap

def orchestrate(config, spark, bootstrap_mode):
    # Determine if we are in bootstrap mode (200GB load)
    spark_bootstrap = spark.conf.get("spark.app.is_bootstrap", "false") == "true"
    is_bootstrap = bootstrap_mode or spark_bootstrap

    dba = IcebergTableManager(spark, config)
    strategy = LaymanSPYStrategy(underlying="SPY")
    logger.info("Starting Pipeline: %s", config.get('project.name'))

    # --- 2. INFRASTRUCTURE SETUP ---
    # Ensures the database/namespace exists in Iceberg
    dba.setup_infrastructure()

    # --- 3. INGESTION (BRONZE) ---
    # Factory provides the correct adapter (CSV/Parquet)
    adapter = AdapterFactory.get_adapter(config.raw_data_format, spark, config)

    # Ingest raw data into the Bronze table
    logger.info("Ingesting raw data from: %s", config.raw_data_path)
    raw_df = adapter.ingest(path=config.raw_data_path, is_bootstrap=is_bootstrap)
    logger.info("Bronze Table Record Count: %s", raw_df.count())

    # --- 4. TRANSFORMATION (SILVER) ---
    # We use the DataFrame API here to prevent "Bus Errors"
    target_silver_table = f"{dba.db_prefix}.filtered_date"
    logger.info("Materializing Silver Layer: %s", target_silver_table)

    # a. Load from Bronze
    bronze_df = spark.table(f"{dba.db_prefix}.{config.table_name}")

    # b. Add business columns (Trade Date and Expiry Date)
    # Expiry is extracted from the OSI symbol (YYMMDD at index 7)
    refined_df = bronze_df.withColumn(
        "expiry_date", F.to_date(F.substring(F.col("symbol"), 7, 6), "yyMMdd")
    ).withColumn(
        "trade_date", F.to_date(F.col("ts_recv"))
    )

    # c. Apply 0DTE Filter and Write to Iceberg
    # Partitioning by trade_date is critical for 200GB performance
    refined_df.filter("trade_date = expiry_date") \
        .writeTo(target_silver_table) \
        .partitionedBy(F.col("trade_date")) \
        .createOrReplace()

    # --- 5. STRATEGY (GOLD) ---
    # Retrieve the refined silver data for signal generation
    silver_df = spark.table(target_silver_table)
    logger.info("Silver Table Record Count (0DTE): %s", silver_df.count())

    # Apply strategy logic (defined in LaymanSPYStrategy)
    gold_df = strategy.generate_signals(silver_df)

    # Finalize the Gold Layer
    gold_table_path = f"{dba.db_prefix}.strategy_signals"
    logger.info("Materializing Gold Layer: %s", gold_table_path)
    gold_df.writeTo(gold_table_path).createOrReplace()

    logger.info(f"Pipeline Orchestration Complete. Medallion layers materialized.")

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