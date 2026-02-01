from src.adapters.csv_adapter import CSVAdapter
from src.adapters.parquet_adapter import ParquetIngestor

class IngestorFactory:
    @staticmethod
    def get_ingestor(format_type: str, spark, config):
        """
        Routes to the correct Adapter based on 'raw_data_format'.
        Passes 'config' so the adapter knows the Iceberg table paths.
        """
        format_type = format_type.lower()
        if format_type == "csv":
            return CSVAdapter(spark, config)
        elif format_type == "parquet":
            pass
        else:
            raise ValueError(f"Unsupported ingestion format: {format_type}")