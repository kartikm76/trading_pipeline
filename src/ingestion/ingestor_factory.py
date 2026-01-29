from src.ingestion.csv_ingestor import  CSVIngestor
from src.ingestion.parquet_ingestor import ParquetIngestor

class IngestorFactory:
    @staticmethod
    def get_ingestor(format_type: str, spark):
        format_type = format_type.lower()
        if format_type == "csv":
            return CSVIngestor(spark)
        elif format_type == "parquet":
            return ParquetIngestor(spark)
        else:
            raise ValueError(f"Unsupported ingestion format: {format_type}")