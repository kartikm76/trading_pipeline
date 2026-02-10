from abc import ABC, abstractmethod
from pyspark.sql import DataFrame
import polars as pl

class BaseStrategy(ABC):
    @property
    @abstractmethod
    def required_columns(self):
        """List of columns to fetch from Silver to minimize memory footprint."""
        pass

    @abstractmethod
    def logic(selfs, ldf: pl.LazyFrame) -> pl.LazyFrame:
        """The core Polars-based computation engine."""
        pass


    @abstractmethod
    def generate_signals(self, df: DataFrame) -> DataFrame:
        """
        Takes market data and returns a DataFrame of Buy/Sell signals.
        Resulting DF should include: [timestamp, symbol, signal, price]
        """
        pass