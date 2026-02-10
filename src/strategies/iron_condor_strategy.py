import polars as pl
from pyspark.sql import DataFrame
from strategies.base_strategy import BaseStrategy

class IronCondorStrategy(BaseStrategy):
    def __init__(self, config):
        self.config = config
        self.underlying = underlying

    @property
    def required_columns (self):
        # Using the exact field names from your schema
        return ["symbol", "trade_date", "expiration", "strike", "option_type", "delta", "mid_price"]

    def generate_signals(self, df: DataFrame) -> DataFrame:
        # Define the output schema for the Spark table
        output_schema = (
            "symbol STRING, trade_date DATE, expiration DATE, "
            "strike_short_call DOUBLE, price_short_call DOUBLE, "
            "strike_long_call DOUBLE, price_long_call DOUBLE, "
            "strike_short_put DOUBLE, price_short_put DOUBLE, "
            "strike_long_put DOUBLE, price_long_put DOUBLE, "
            "net_credit DOUBLE, strategy_name STRING, underlying STRING"
        )

        # # Optimization: Filter for only the required columns BEFORE sending to EMR executors
        return df.select(*self.required_columns).mapInPandas(
            self._process_partition, schema=output_schema
        )

    def _process_partition(self, pdf_iterator):
        for pdf in pdf_iterator:
            if pdf.empty:
                continue

            # Convert partition to Polars LazyFrame (ldf)
            ldf = pl.from_pandas(pdf).lazy()

            calls = ldf.filter(pl.col("option_type") == "CALL")
            puts = ldf.filter(pl.col("option_type") == "PUT")

            def get_leg(df, target, suffix):
                return (df.with_columns(dist=(pl.col("delta").abs() - target).abs())
                        .sort("dist")
                        .group_by(["symbol", "trade_date", "expiration"])
                        .head(1)
                        .select([
                            pl.col("symbol"),
                            pl.col("trade_date"),
                            pl.col("expiration"),
                            pl.col("strike").alias(f"strike_{suffix}"),
                            pl.col("mid_price").alias(f"price_{suffix}")
                        ]))
            # 45 Delta Shorts, 40 Delta Longs
            s_c = get_leg(calls, 0.45, "short_call")
            l_c = get_leg(calls, 0.40, "long_call")
            s_p = get_leg(puts, 0.45, "short_put")
            l_p = get_leg(puts, 0.40, "long_put")

            # Join and Calculate Net Credit
            res = s_c.join(l_c, on=["symbol", "trade_date", "expiration"]) \
                .join(s_p, on=["symbol", "trade_date", "expiration"]) \
                .join(l_p, on=["symbol", "trade_date", "expiration"]) \
                .with_columns(
                net_credit=((pl.col("price_short_put") + pl.col("price_short_call")) -
                            (pl.col("price_long_put") + pl.col("price_long_call"))).round(2),
                strategy_name=pl.lit("IRON_CONDOR"),
                underlying=pl.lit(self.underlying)
            )

            yield res.collect().to_pandas()