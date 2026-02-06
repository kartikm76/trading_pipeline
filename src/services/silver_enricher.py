from pyspark.sql import DataFrame, functions as F
import filters

class SilverEnricher:
    def __init__(self, config):
        self.config = config

    # Enriches and filters the bronze DataFrame
    # Enrichment will bring in columns like option_type, expiry_date, etc. - easy to use in filtering
    # If filter is done first; then OSI Symbol will have to decomposed on the fly for every record

    def process(self, bronze_df: DataFrame) -> DataFrame:
        # Get underlying mapping from config
        underlying_mapping = self.config.underlying_mapping

        # Create PySpark mapping expression
        mapping_expr = F.create_map([F.lit(x) for pair in underlying_mapping.items() for x in pair])

        # Add enriched columns
        enriched_df = (bronze_df
                       # Extract underlying symbol (first 6 chars, trimmed)
                       .withColumn("symbol_raw", F.trim(F.substring(F.col("symbol"), 1, 6)))
                       .withColumn("underlying", F.coalesce(mapping_expr[F.col("symbol_raw")], F.col("symbol_raw")))
                       # Extract trade_date from filename: opra-pillar-20250128.cbbo-1m.csv -> 20250128
                       .withColumn("trade_date", F.to_date(F.regexp_extract(F.col("file_name"), r"(\d{8})", 1), "yyyyMMdd"))
                       # Extract expiry_date from symbol: position 7, length 6 (YYMMDD format)
                       .withColumn("expiry_date", F.to_date(F.substring(F.col("symbol"), 7, 6), "yyMMdd"))
                       # Extract option_type: position 13 (C or P)
                       .withColumn("option_type", F.when(F.substring(F.col("symbol"), 13, 1) == "C", "CALL").otherwise("PUT"))
                       # Extract strike_price: position 14, length 8, divide by 1000
                       .withColumn("strike_price", (F.substring(F.col("symbol"), 14, 8).cast("decimal(10,2)") / 1000))
                       # Calculate mid_price
                       .withColumn("mid_price",
                                   ((F.col("bid_px_00").cast("decimal(10,2)") + F.col("ask_px_00").cast("decimal(10,2)")) / 2)))

        # Reorder columns: symbol, underlying, trade_date, expiry_date, option_type, strike_price,
        # then all bronze columns (except symbol and file_name), then mid_price, then file_name
        bronze_cols = [col for col in bronze_df.columns if col not in ["symbol", "file_name"]]
        enriched_df = enriched_df.select(
                        "symbol",
                        "underlying",
                        "trade_date",
                        "expiry_date",
                        "option_type",
                        "strike_price",
                        *bronze_cols,
                        "mid_price",
                        "file_name"
        )

        # 2. Dynamic Policy Invocation (Strategy Switchboard)
        filtered_df = enriched_df
        active_filters = self.config.active_filter_classes
        for filter_name in active_filters:
            filter_class = getattr(filters, filter_name)
            filtered_df = filter_class().apply(filtered_df)
        return filtered_df