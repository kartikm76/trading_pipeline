from abc import ABC, abstractmethod
from pyspark.sql import DataFrame

class BaseStrategy(ABC):
    @abstractmethod
    def generate_signals(self, df: DataFrame) -> DataFrame:
        """
        Takes market data and returns a DataFrame of Buy/Sell signals.
        Resulting DF should include: [timestamp, symbol, signal, price]
        """
        pass