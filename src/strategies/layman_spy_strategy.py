from pyspark.sql import DataFrame, functions as F
from strategies.base_strategy import BaseStrategy

class LaymanSPYStrategy(BaseStrategy):
    def __init__(self, underlying: str):
        self.underlying = underlying

    def generate_signals(self, df: DataFrame) -> DataFrame:
        # 1. Apply Strategy Logic
        signals_df = df.withColumn(
            "signal",
            F.when(
                (F.col("option_type") == "PUT") & (F.col("mid_price") > 1.00), "SELL_PUT"
            ).when(
                (F.col("option_type") == "CALL") & (F.col("mid_price") > 1.00), "BUY_CALL"
            ).otherwise("HOLD")
        )

        # 2. Return the strategy output
        return signals_df.select(
            "ts_recv",
            "symbol",
            "option_type",
            "bid_px_00",
            "ask_px_00",
            "mid_price",
            "signal"
        )