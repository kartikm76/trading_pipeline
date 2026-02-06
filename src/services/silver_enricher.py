from pyspark.sql import DataFrame, functions as F
import filters

class SilverEnricher:
    def __init__(self, config):
        self.config = config

    # Enriches and filters the bronze DataFrame
    # Enrichment will bring in columns like option_type, expiry_date, etc. - easy to use in filtering
    # If filter is done first; then OSI Symbol will have to decomposed on the fly for every record

    def process(self, bronze_df: DataFrame) -> DataFrame:
        enriched_df = bronze_df.withColumn("trade_date", F.to_date(F.split(F.col("file_name"), "_").getItem(0))) \
                        .withColumn("expiry_date", F.to_date(F.substring(F.col("symbol"), 4, 6), "yyMMdd")) \
                        .withColumn("option_type", F.when(F.col("symbol").contains("C"), "CALL").otherwise("PUT")) \
                        .withColumn("mid_price", (F.col("bid_px_00") + F.col("ask_px_00")) / 2)

        # 2. Dynamic Policy Invocation (Strategy Switchboard)
        filtered_df = enriched_df
        active_filters = self.config.active_filter_classes
        for filter_name in active_filters:
            filter_class = getattr(filters, filter_name)
            filtered_df = filter_class().apply(filtered_df)
        return filtered_df