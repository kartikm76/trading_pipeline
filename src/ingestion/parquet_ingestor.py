from src.ingestion.base_ingestor import BaseIngestor
from pyspark.sql import DataFrame

class ParquetIngestor(BaseIngestor):
    def ingest(self, path: str) -> DataFrame:
        print(f"Executing Parquet Ingestion from: {path}")
        # mergeSchema is set to false for performance; set to true if schema evolves
        return self.spark.read \
                .option("mergeSchema", "false") \
                .parquet(path)