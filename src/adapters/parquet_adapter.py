from pyspark.sql import SparkSession, DataFrame
from adapters.base_adapter import BaseAdapter

class ParquetAdapter(BaseAdapter):
    def __init__(self, spark: SparkSession, config):
        self.spark = spark
        self.config = config
        # Path built once from config to avoid repeated lookups
        self.full_table_path = f"{config.catalog}.{config.db_name}.{config.table_name}"

    def ingest(self, path: str, is_bootstrap: bool = False) -> DataFrame:
        print(f"Executing Parquet Ingestion from: {path}")
        # mergeSchema is set to false for performance; set to true if schema evolves
        return self.spark.read \
                .option("mergeSchema", "false") \
                .parquet(path)

    def get_options_data(self, ticker: str, start_date: str, end_date: str) -> DataFrame:
        raise NotImplementedError("ParquetAdapter does not support get_options_data.")