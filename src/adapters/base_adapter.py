from abc import ABC, abstractmethod
from pyspark.sql import DataFrame

class BaseAdapter(ABC):
    """
    Standard interface for all market data providers
    """
    @abstractmethod
    def get_options_data(self, ticker: str, start_date: str, end_date: str) -> DataFrame:
        """
        Must return a Spark DataFrame with columns:
        [timestamp, symbol, strike, expiry, put_call, bid, ask, last_price, underlying_price]
        """
        pass