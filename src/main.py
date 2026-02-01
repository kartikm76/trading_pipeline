from adapters.adapter_factory import IngestorFactory
from src.strategies.layman_spy_strategy import LaymanSPYStrategy
from src.config import SparkSessionBuilder, ConfigManager
from src.utils.iceberg_setup import IcebergTableManager
import argparse

def main():
    #0 -- Capture bootstrap flag
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true", help="Run initial 200GB load")
    args, unknown = parser.parse_known_args()

    # --- 1. INITIALIZATION ---
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()

    # Try to get the flag from Spark properties (set by the shell script)
    # or fall back to the CLI argument (used in local dev)
    spark_bootstrap = spark.conf.get("spark.app.is_bootstrap", "false") == "true"
    is_bootstrap = args.bootstrap or spark_bootstrap

    # Delegate Initialization
    dba = IcebergTableManager(spark, config)
    strategy = LaymanSPYStrategy(underlying="SPY")

    print(f"🚀 Starting Pipeline: {config.get('project.name')}")

    # --- 2. INFRASTRUCTURE SETUP ---
    dba.setup_infrastructure() # [cite: 75]

    # -- 3. Factory uses the new explicit 'raw_data_format' (csv)
    ingestor = IngestorFactory.get_ingestor(config.raw_data_format, spark, config)

    # --4. Use the adapter to load raw data
    raw_df = ingestor.ingest(path = config.raw_data_path, is_bootstrap=is_bootstrap)

    # --- 4. TRANSFORMATION (SILVER) ---
    # We now use the 'materialize_view' mechanism for ALL business policies.

    # Policy 1: 0DTE Filter
    dba.materialize_view(
        source_table=config.table_name,
        target_table="filtered_date",
        criteria="`Trade Date` = `Expiry Date`" # [cite: 85]
    )

    # Policy 2: Out-of-the-Money (OTM) Filter
    # Injected dynamically through the same infrastructure delegate
    # dba.materialize_view(
    #     source_table="filtered_date",
    #     target_table="filtered_otm",
    #     criteria="Strike > UnderlyingPrice" # [cite: 85]
    # )

    # --- 5. STRATEGY (GOLD) ---
    # Retrieve the refined silver data for signal generation
    silver_df = spark.table(f"{dba.db_prefix}.filtered_date")

    gold_df = strategy.generate_signals(silver_df) # [cite: 59, 60]
    gold_df.writeTo(f"{dba.db_prefix}.strategy_signals").createOrReplace()

    print("✅ Pipeline Orchestration Complete. All layers materialized in Iceberg.")
    SparkSessionBuilder.stop()

if __name__ == "__main__":
    main()