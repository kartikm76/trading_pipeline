from pyspark.sql import SparkSession, DataFrame, functions as F
from adapters.base_adapter import BaseAdapter
from adapters.data_loader import PRODUCTION_SCHEMA

class CSVAdapter(BaseAdapter):
    def __init__(self, spark: SparkSession, config):
        self.spark = spark
        self.config = config
        # Path built once from config to avoid repeated lookups
        self.full_table_path = f"{config.catalog}.{config.db_name}.{config.table_name}"

    def ingest(self, path: str, is_bootstrap: bool = False) -> DataFrame:
        """
        Loads 200GB raw CSVs and writes them to Iceberg Parquet.
        """
        # 1. Load using the explicit PRODUCTION_SCHEMA (No inferSchema scan)
        df = self.spark.read.csv(
            path,
            schema=PRODUCTION_SCHEMA,
            header=True
        )

        # 2. Optimized Iceberg Write
        writer = df.writeTo(self.full_table_path)

        if is_bootstrap:
            # Scale-optimized for 200GB initial load
            writer.tableProperty("format-version", "2") \
                .tableProperty("write.format.default", self.config.iceberg_format) \
                .tableProperty("write.update.mode", "merge-on-read") \
                .partitionedBy(F.days("ts_recv")) \
                .createOrReplace()
        else:
            # 3-minute target for 5GB daily deltas
            writer.append()
        return df

    def get_options_data(self, ticker: str, start_date: str, end_date: str) -> DataFrame:
        return self.spark.table(self.full_table_path) \
            .filter(F.col("symbol") == ticker) \
            .filter(F.col("ts_recv").between(start_date, end_date))