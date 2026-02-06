from abc import ABC

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from adapters.base_adapter import BaseAdapter

class CSVAdapter(BaseAdapter, ABC):
    def __init__(self, spark: SparkSession, config):
        self.spark = spark
        self.config = config
        # Path built once from config to avoid repeated lookups
        self.full_table_path = config.get_table_path('bronze')
        self.raw_format = config.raw_format

    # Inside your CSV/Parquet Adapter class
    def ingest(self, path: str, is_bootstrap: bool = False) -> DataFrame:
        df = self.spark.read.format(self.raw_format).option("header", "true").option("inferSchema", "true").load(path)

        # Add file_name column - extract just the filename from the full path
        # input_file_name() returns the full path, we extract just the filename
        df = df.withColumn("file_name", F.regexp_extract(F.input_file_name(), r"([^/]+)$", 1))

        target_table = self.config.get_table_path('bronze')

        writer = df.writeTo(target_table)

        if is_bootstrap:
            # Add .using("iceberg") so Spark knows how to create the new table
            writer.using("iceberg").tableProperty("format-version", "2").createOrReplace()
        else:
            # Only use append once the table exists
            writer.append()

        return self.spark.table(target_table)

    def get_options_data(self, ticker: str, start_date: str, end_date: str) -> DataFrame:
        raise NotImplementedError("CSVAdapter does not support get_options_data.")