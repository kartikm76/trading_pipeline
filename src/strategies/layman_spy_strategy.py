from pyspark.sql import DataFrame, functions as F
from strategies.base_strategy import BaseStrategy

class LaymanSPYStrategy(BaseStrategy):
    def __init__(self, underlying: str):
        self.underlying = underlying

    def generate_signals(self, df: DataFrame) -> DataFrame:
        # 1. Parse Option Type from OSI Symbol string [cite: 137]
        df = df.withColumn(
            "option_type",
            F.when(F.col("symbol").contains("C"), "CALL")
            .when(F.col("symbol").contains("P"), "PUT")
            .otherwise("UNKNOWN")
        )

        # 2. Calculate Mid-Price for valuation using raw schema [cite: 137]
        df = df.withColumn(
            "mid_price",
            (F.col("bid_px_00") + F.col("ask_px_00")) / 2
        )

        # 3. Apply Trading Logic using Column expressions (Fixes IDE errors)
        signals_df = df.withColumn(
            "signal",
            F.when(
                (F.col("option_type") == "PUT") & (F.col("mid_price") > 1.00), "SELL_PUT"
            ).when(
                (F.col("option_type") == "CALL") & (F.col("mid_price") > 1.00), "BUY_CALL"
            ).otherwise("HOLD")
        )

        # 4. Filter for specific strategy output
        return signals_df.select(
            "ts_recv",
            "symbol",
            "option_type",
            "bid_px_00",
            "ask_px_00",
            "mid_price",
            "signal"
        )