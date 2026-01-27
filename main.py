from src.strategies.layman_spy_strategy import LaymanSPYStrategy
from src.config import SparkSessionBuilder, ConfigManager

def main():
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()

    # 1. BRONZE: Ingest Raw CSV
    print(f"Ingesting raw data from {config.raw_data_path}...")
    raw_df = spark.read.option("header", "true").option("inferSchema", "true").csv(config.raw_data_path)
    raw_df.writeTo(f"{config.catalog}.{config.db_name}.raw_options_chain").createOrReplace()

    # 2. SILVER: Filter for 0DTE
    # Note: Use backticks if your CSV columns have spaces like 'Trade Date'
    spark.sql(f"""
        CREATE OR REPLACE TABLE {config.catalog}.{config.db_name}.filtered_0dte AS
        SELECT * FROM {config.catalog}.{config.db_name}.raw_options_chain
        WHERE `Trade Date` = `Expiry Date`
    """)

    # 3. GOLD: Run Strategy
    silver_df = spark.table(f"{config.catalog}.{config.db_name}.filtered_0dte")
    strategy = LaymanSPYStrategy(underlying="SPY")
    gold_df = strategy.generate_signals(silver_df)
    gold_df.writeTo(f"{config.catalog}.{config.db_name}.strategy_signals").createOrReplace()

    print("✓ Local Test Successful. Results in ./iceberg-warehouse/")
    SparkSessionBuilder.stop()

if __name__ == "__main__":
    main()