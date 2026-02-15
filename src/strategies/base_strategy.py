from abc import ABC, abstractmethod
from decimal import Decimal
from pyspark.sql import DataFrame
import polars as pl
import pandas as pd

# Columns that come as Decimal from Iceberg and need float64 conversion
DECIMAL_COLUMNS = ["strike_price", "mid_price", "price", "bid_px_00", "ask_px_00",
                   "bid_pb_00", "ask_pb_00"]

class BaseStrategy(ABC):
    # Default lookback: 7 days. Override in subclass for wider/narrower windows.
    lookback_days: int = 7

    @property
    @abstractmethod
    def required_columns(self):
        """List of columns to fetch from Silver to minimize memory footprint."""
        pass

    @abstractmethod
    def logic(self, ldf: pl.LazyFrame) -> pl.LazyFrame:
        """The core Polars-based computation engine."""
        pass


    @abstractmethod
    def generate_signals(self, df: DataFrame) -> DataFrame:
        """
        Takes market data and returns a DataFrame of Buy/Sell signals.
        Resulting DF should include: [timestamp, symbol, signal, price]
        """
        pass

    @staticmethod
    def cast_decimals(pdf: pd.DataFrame) -> pd.DataFrame:
        """Cast Iceberg Decimal columns to float64 for Polars/Arrow compatibility."""
        for col in DECIMAL_COLUMNS:
            if col in pdf.columns:
                pdf[col] = pdf[col].astype(float)
        return pdf