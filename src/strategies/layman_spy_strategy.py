import polars as pl
from pyspark.sql import DataFrame
from strategies.base_strategy import BaseStrategy

class LaymanSPYStrategy(BaseStrategy):
    def __init__(self, config, underlying):
        self.config = config
        self.underlying = underlying

    @property
    def required_columns(self):
        # Minimal set for a lightweight test
        return ["symbol", "trade_date", "expiration", "strike", "option_type", "mid_price"]

    def generate_signals(self, df: DataFrame) -> DataFrame:
        output_schema = (
            "symbol STRING, trade_date DATE, expiration DATE, "
            "strike DOUBLE, mid_price DOUBLE, option_type STRING, "
            "strategy_name STRING, underlying STRING"
        )

        return df.select(*self.required_columns).mapInPandas(
            self._process_partition, schema=output_schema
        )

    def _process_partition(self, pdf_iterator):
        for pdf in pdf_iterator:
            if pdf.empty:
                continue

            ldf = pl.from_pandas(pdf).lazy()

            # Lightweight Logic: Just pick the first CALL for each date
            # This proves the Polars -> Spark -> Gold pipeline is working
            res = (
                ldf.filter(pl.col("option_type") == "CALL")
                .group_by(["symbol", "trade_date", "expiration"])
                .head(1)
                .with_columns(
                    strategy_name=pl.lit("LAYMAN_SPY"),
                    underlying=pl.lit(self.underlying)
                )
            )

            yield res.collect().to_pandas()