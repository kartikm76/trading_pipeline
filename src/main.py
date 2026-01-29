from src.ingestion.ingestor_factory import IngestorFactory
from src.strategies.layman_spy_strategy import LaymanSPYStrategy
from src.config import SparkSessionBuilder, ConfigManager
from src.utils.iceberg_setup import IcebergTableManager

def main():
    # --- 1. INITIALIZATION ---
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()

    # Delegate Initialization
    dba = IcebergTableManager(spark, config)
    strategy = LaymanSPYStrategy(underlying="SPY")

    print(f"🚀 Starting Pipeline: {config.get('project.name')}")

    # --- 2. INFRASTRUCTURE SETUP ---
    dba.setup_infrastructure() # [cite: 75]

    # --- 3. INGESTION (BRONZE) ---
    ingestor = IngestorFactory.get_ingestor(config.data_format, spark) # [cite: 36]
    raw_df = ingestor.ingest(config.raw_data_path) # [cite: 37]

    # Standardize writing to the Bronze table defined in config
    raw_df.writeTo(f"{dba.db_prefix}.{config.table_name}").createOrReplace()

    # --- 4. TRANSFORMATION (SILVER) ---
    # We now use the 'materialize_view' mechanism for ALL business policies.

    # Policy 1: 0DTE Filter
    dba.materialize_view(
        source_table=config.table_name,
        target_table="filtered_0dte",
        criteria="`Trade Date` = `Expiry Date`" # [cite: 85]
    )

    # Policy 2: Out-of-the-Money (OTM) Filter
    # Injected dynamically through the same infrastructure delegate
    # dba.materialize_view(
    #     source_table="filtered_0dte",
    #     target_table="filtered_otm",
    #     criteria="Strike > UnderlyingPrice" # [cite: 85]
    # )

    # --- 5. STRATEGY (GOLD) ---
    # Retrieve the refined silver data for signal generation
    silver_df = spark.table(f"{dba.db_prefix}.filtered_otm")

    gold_df = strategy.generate_signals(silver_df) # [cite: 59, 60]
    gold_df.writeTo(f"{dba.db_prefix}.strategy_signals").createOrReplace()

    print("✅ Pipeline Orchestration Complete. All layers materialized in Iceberg.")
    SparkSessionBuilder.stop()

if __name__ == "__main__":
    main()