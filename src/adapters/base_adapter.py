from abc import ABC, abstractmethod
from pyspark.sql import DataFrame

class BaseAdapter(ABC):
    """
    Standard interface for all market data providers
    """
    @abstractmethod
    def ingest(self, path: str, is_bootstrap: bool = False) -> DataFrame:
        """Standardized method to load data and write to Iceberg."""
        pass

    @abstractmethod
    def get_options_data(self, ticker: str, start_date: str, end_date: str) -> DataFrame:
        pass