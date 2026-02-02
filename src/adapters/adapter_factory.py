from  adapters.csv_adapter import CSVAdapter
from adapters.parquet_adapter import ParquetAdapter
from adapters.polygen_adapter import PolygonAdapter

class AdapterFactory:
    @staticmethod
    def get_adapter(format_type: str, spark, config):
        """
        Routes to the correct Adapter based on 'raw_data_format'.
        Passes 'config' so the adapter knows the Iceberg table paths.
        """
        format_type = format_type.lower()
        if format_type == "csv":
            return CSVAdapter(spark, config)
        elif format_type == "parquet":
            return ParquetAdapter(spark, config)
        elif format_type == "polygon":
            return PolygonAdapter(spark, config)
        else:
            raise ValueError(f"Unsupported ingestion format: {format_type}")