from pyspark.sql import SparkSession, DataFrame
from src.adapters.base_adapter import BaseAdapter

class ParquetIngestor(BaseAdapter):
    def __init__(self, spark: SparkSession, config: dict):
        self.spark = spark
        self.config = config
        # Path built once from config to avoid repeated lookups
        self.full_table_path = f"{config['storage']['catalog_name']}.{config['storage']['db_name']}.{config['storage']['table_name']}"

    def ingest(self, path: str, is_bootstrap: bool = False) -> DataFrame:
        print(f"Executing Parquet Ingestion from: {path}")
        # mergeSchema is set to false for performance; set to true if schema evolves
        return self.spark.read \
                .option("mergeSchema", "false") \
                .parquet(path)