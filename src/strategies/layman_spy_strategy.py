import polars as pl
from pyspark.sql import DataFrame
from strategies.base_strategy import BaseStrategy

class LaymanSPYStrategy(BaseStrategy):
    """
    Lightweight test strategy to validate the full pipeline:
      Silver → Polars (mapInPandas) → Gold Iceberg table

    Logic: Simple mid_price threshold signal generation.
      - CALL options with mid_price < 5.0  → BUY_CALL  (cheap calls)
      - PUT  options with mid_price < 5.0  → BUY_PUT   (cheap puts)
      - Everything else                    → HOLD
    """

    def __init__(self, config, underlying):
        self.config = config
        self.underlying = underlying

    @property
    def required_columns(self):
        return ["symbol", "trade_date", "expiration", "strike", "option_type", "mid_price"]

    def logic(self, ldf: pl.LazyFrame) -> pl.LazyFrame:
        """Core Polars logic — generates a signal column based on price thresholds."""
        return ldf.with_columns(
            pl.when((pl.col("option_type") == "CALL") & (pl.col("mid_price") < 5.0))
              .then(pl.lit("BUY_CALL"))
              .when((pl.col("option_type") == "PUT") & (pl.col("mid_price") < 5.0))
              .then(pl.lit("BUY_PUT"))
              .otherwise(pl.lit("HOLD"))
              .alias("signal")
        ).with_columns(
            strategy_name=pl.lit("LAYMAN_SPY"),
            underlying=pl.lit(self.underlying)
        )

    def generate_signals(self, df: DataFrame) -> DataFrame:
        output_schema = (
            "symbol STRING, trade_date DATE, expiration DATE, "
            "strike DOUBLE, mid_price DOUBLE, option_type STRING, "
            "signal STRING, strategy_name STRING, underlying STRING"
        )

        return df.select(*self.required_columns).mapInPandas(
            self._process_partition, schema=output_schema
        )

    def _process_partition(self, pdf_iterator):
        for pdf in pdf_iterator:
            if pdf.empty:
                continue

            ldf = pl.from_pandas(pdf).lazy()
            res = self.logic(ldf)
            yield res.collect().to_pandas()