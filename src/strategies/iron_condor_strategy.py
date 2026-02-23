import logging
import polars as pl
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class IronCondorStrategy(BaseStrategy):
    lookback_days = 30  # 30-day lookback window for iron condor analysis

    def __init__(self, config, underlying):
        self.config = config
        self.underlying = underlying

    @property
    def required_columns(self):
        return ["symbol", "trade_date", "expiry_date", "strike_price", "option_type", "mid_price"]

    def logic(self, ldf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Core Polars logic — constructs iron condor by selecting 4 option legs.

        Iron Condor structure:
          - Short Call: highest call strike
          - Long Call:  2nd highest call strike (wider protection)
          - Short Put:  lowest put strike
          - Long Put:   2nd lowest put strike (wider protection)

        IMPORTANT: Each partition is guaranteed to contain complete
        (symbol, trade_date, expiry_date) groups because generate_signals()
        repartitions by those keys before calling mapInPandas.
        """
        # --- Validate: keep only groups with 2+ call strikes AND 2+ put strikes ---
        call_counts = ldf.filter(pl.col("option_type") == "CALL") \
            .group_by(["symbol", "trade_date", "expiry_date"]) \
            .agg(pl.col("strike_price").n_unique().alias("num_calls"))

        put_counts = ldf.filter(pl.col("option_type") == "PUT") \
            .group_by(["symbol", "trade_date", "expiry_date"]) \
            .agg(pl.col("strike_price").n_unique().alias("num_puts"))

        valid_combos = call_counts.join(
            put_counts, on=["symbol", "trade_date", "expiry_date"], how="inner"
        ).filter(
            (pl.col("num_calls") >= 2) & (pl.col("num_puts") >= 2)
        ).select(["symbol", "trade_date", "expiry_date"])

        ldf = ldf.join(valid_combos, on=["symbol", "trade_date", "expiry_date"], how="inner")

        # --- Split into calls / puts ---
        calls = ldf.filter(pl.col("option_type") == "CALL")
        puts = ldf.filter(pl.col("option_type") == "PUT")

        # --- Rank call strikes descending (1 = highest) ---
        calls_ranked = calls.with_columns(
            strike_rank=pl.col("strike_price")
                .rank(method="ordinal", descending=True)
                .over(["symbol", "trade_date", "expiry_date"])
        )

        s_c = calls_ranked.filter(pl.col("strike_rank") == 1).select([
            pl.col("symbol"), pl.col("trade_date"), pl.col("expiry_date"),
            pl.col("strike_price").alias("strike_short_call"),
            pl.col("mid_price").alias("price_short_call"),
        ])

        l_c = calls_ranked.filter(pl.col("strike_rank") == 2).select([
            pl.col("symbol"), pl.col("trade_date"), pl.col("expiry_date"),
            pl.col("strike_price").alias("strike_long_call"),
            pl.col("mid_price").alias("price_long_call"),
        ])

        # --- Rank put strikes ascending (1 = lowest) ---
        puts_ranked = puts.with_columns(
            strike_rank=pl.col("strike_price")
                .rank(method="ordinal", descending=False)
                .over(["symbol", "trade_date", "expiry_date"])
        )

        s_p = puts_ranked.filter(pl.col("strike_rank") == 1).select([
            pl.col("symbol"), pl.col("trade_date"), pl.col("expiry_date"),
            pl.col("strike_price").alias("strike_short_put"),
            pl.col("mid_price").alias("price_short_put"),
        ])

        l_p = puts_ranked.filter(pl.col("strike_rank") == 2).select([
            pl.col("symbol"), pl.col("trade_date"), pl.col("expiry_date"),
            pl.col("strike_price").alias("strike_long_put"),
            pl.col("mid_price").alias("price_long_put"),
        ])

        # --- Join all 4 legs ---
        res = s_c.join(l_c, on=["symbol", "trade_date", "expiry_date"], how="inner") \
                 .join(s_p, on=["symbol", "trade_date", "expiry_date"], how="inner") \
                 .join(l_p, on=["symbol", "trade_date", "expiry_date"], how="inner") \
                 .select([
                     pl.col("symbol"), pl.col("trade_date"), pl.col("expiry_date"),
                     pl.col("strike_short_call"), pl.col("price_short_call"),
                     pl.col("strike_long_call"),  pl.col("price_long_call"),
                     pl.col("strike_short_put"),  pl.col("price_short_put"),
                     pl.col("strike_long_put"),   pl.col("price_long_put"),
                 ]) \
                 .with_columns(
                     net_credit=((pl.col("price_short_put") + pl.col("price_short_call"))
                                 - (pl.col("price_long_put") + pl.col("price_long_call"))).round(2),
                     strategy_name=pl.lit("IRON_CONDOR"),
                     underlying=pl.lit(self.underlying),
                 ) \
                 .rename({"expiry_date": "expiration"})

        return res

    def generate_signals(self, df: DataFrame) -> DataFrame:
        input_count = df.count()
        logger.info(f"🔍 generate_signals() received {input_count} rows")

        output_schema = (
            "symbol STRING, trade_date DATE, expiration DATE, "
            "strike_short_call DOUBLE, price_short_call DOUBLE, "
            "strike_long_call DOUBLE, price_long_call DOUBLE, "
            "strike_short_put DOUBLE, price_short_put DOUBLE, "
            "strike_long_put DOUBLE, price_long_put DOUBLE, "
            "net_credit DOUBLE, strategy_name STRING, underlying STRING"
        )

        filtered_df = df.select(*self.required_columns)

        # ── KEY FIX: repartition by group key so each partition has ──
        # ── complete (symbol, trade_date, expiry_date) groups       ──
        grouped_df = filtered_df.repartition(F.col("symbol"), F.col("trade_date"), F.col("expiry_date"))
        logger.info("Repartitioned by (symbol, trade_date, expiry_date)")

        result = grouped_df.mapInPandas(self._process_partition, schema=output_schema)

        result_count = result.count()
        logger.info(f"✅ Final iron-condor signals: {result_count} rows")

        return result

    def _process_partition(self, pdf_iterator):
        import logging
        log = logging.getLogger("IronCondorStrategy.executor")

        partition_num = 0
        for pdf in pdf_iterator:
            partition_num += 1
            if pdf.empty:
                log.info(f"Partition {partition_num}: empty, skipping")
                continue

            log.info(f"Partition {partition_num}: {len(pdf)} input rows")
            try:
                pdf = self.cast_decimals(pdf)
                ldf = pl.from_pandas(pdf).lazy()
                res = self.logic(ldf)
                result_pdf = res.collect().to_pandas()
                log.info(f"Partition {partition_num}: yielding {len(result_pdf)} iron condor signals")
                yield result_pdf
            except Exception as e:
                log.error(f"Partition {partition_num}: {type(e).__name__}: {e}", exc_info=True)
                continue