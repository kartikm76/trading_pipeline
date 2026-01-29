from src.ingestion.base_ingestor import BaseIngestor
from pyspark.sql import DataFrame

class CSVIngestor(BaseIngestor):
    def ingest(self, path: str) -> DataFrame:
        print(f"Executing CSV Ingestion from: {path}")
        return self.spark.read \
                .option("header", "true") \
                .option("inferSchema", "true") \
                .csv(path)