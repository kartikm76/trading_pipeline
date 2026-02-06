from pyspark.sql import DataFrame
from filters.base_filter import FilterPolicy

class ZeroDETEPolicy(FilterPolicy):
    def apply(self, df: DataFrame) -> DataFrame:
        ## logic for matching trade_date and expiry_date
        return df.filter("`trade_date` = `expiry_date`")

class LiquidityPolicy(FilterPolicy):
    def apply(self, df: DataFrame) -> DataFrame:
        ## logic for filtering out stale quotes
        return df.filter("bid_px_00 > 0 AND ask_px_00 > 0")