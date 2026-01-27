from pyspark.sql import DataFrame, functions as F
from src.strategies.base_strategy import BaseStrategy

class LaymanSPYStrategy(BaseStrategy):
    def __init__(self, underlying: str):
        self.underlying = underlying

    def generate_signals(self, df: DataFrame) -> DataFrame:
        # Requirement A & B: Map underlying symbol to the specific option row
        # and create a clear distinction between the ticker and the signal.
        # Simple Logic: If the option 'close' price is high, we 'SELL_PUT' (for high premium)
        # Otherwise, we 'HOLD'.
        signals_df = df.withColumn(
            "underlying_ref", F.lit(self.underlying)
        ).withColumn(
            "signal",
            F.when(
                (F.col("Call/Put") == "Put") &
                (F.col("Delta").between(-0.15, -0.05)) &
                (F.col("Last Trade Price") > 0.50),
                "SELL_PUT"
            )
            .when(
                (F.col("Call/Put") == "Call") &
                (F.col("Delta").between(0.05, 0.15)) &
                (F.col("Last Trade Price") > 0.50),
                "BUY_CALL"
            )
            .otherwise("HOLD")
        )
        # Return relevant columns for analysis
        return signals_df.select(
            "Trade Date",
            "Expiry Date",
            "Strike",
            "Call/Put",
            "Last Trade Price",
            "Delta",
            "Open Interest",
            "Volume",
            "underlying_ref",
            "signal"
        )