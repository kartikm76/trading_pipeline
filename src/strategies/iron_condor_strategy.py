import logging
import polars as pl
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

# The grouping key for iron condor construction.
# We group by (underlying, trade_date, expiry_date) — NOT by symbol,
# because `symbol` is the full OCC option symbol (unique per contract),
# while `underlying` is the root ticker (e.g. SPY) shared across all
# contracts for the same underlying on the same date/expiry.
GROUP_KEY = ["underlying", "trade_date", "expiry_date"]


class IronCondorStrategy(BaseStrategy):
    lookback_days = 30  # 30-day lookback window for iron condor analysis

    def __init__(self, config, underlying):
        self.config = config
        self.underlying = underlying

    @property
    def required_columns(self):
        return ["underlying", "trade_date", "expiry_date", "strike_price", "option_type", "mid_price"]

    def logic(self, ldf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Core Polars logic — constructs iron condor by selecting 4 option legs.

        Iron Condor structure:
          - Short Call: highest call strike
          - Long Call:  2nd highest call strike (wider protection)
          - Short Put:  lowest put strike
          - Long Put:   2nd lowest put strike (wider protection)

        Groups by (underlying, trade_date, expiry_date).
        """
        import logging
        log = logging.getLogger("IronCondorStrategy.logic")

        input_df = ldf.collect()
        log.warning(f"LOGIC INPUT: {len(input_df)} rows")

        # --- Step 0: Drop rows with null mid_price (no usable quote) ---
        clean = input_df.lazy().filter(pl.col("mid_price").is_not_null())

        # --- Step 1: Deduplicate to one row per (group, option_type, strike_price) ---
        # Multiple rows can exist for the same strike (different timestamps, etc.)
        # Take the mean mid_price across duplicates for a stable single value.
        deduped = clean.group_by([*GROUP_KEY, "option_type", "strike_price"]) \
            .agg(pl.col("mid_price").mean().alias("mid_price"))

        deduped_df = deduped.collect()
        log.warning(f"LOGIC after null-filter + dedup: {len(deduped_df)} rows")
        ldf = deduped_df.lazy()

        # --- Step 2: Validate — keep groups with 2+ distinct call AND put strikes ---
        call_counts = ldf.filter(pl.col("option_type") == "CALL") \
            .group_by(GROUP_KEY) \
            .agg(pl.col("strike_price").n_unique().alias("num_calls"))

        put_counts = ldf.filter(pl.col("option_type") == "PUT") \
            .group_by(GROUP_KEY) \
            .agg(pl.col("strike_price").n_unique().alias("num_puts"))

        cc = call_counts.collect()
        pc = put_counts.collect()
        log.warning(f"LOGIC call groups: {len(cc)}, put groups: {len(pc)}")

        valid_combos = cc.lazy().join(
            pc.lazy(), on=GROUP_KEY, how="inner"
        ).filter(
            (pl.col("num_calls") >= 2) & (pl.col("num_puts") >= 2)
        ).select(GROUP_KEY)

        vc = valid_combos.collect()
        log.warning(f"LOGIC valid_combos: {len(vc)} groups")

        if len(vc) == 0:
            log.warning("LOGIC: 0 valid combos — returning empty frame")
            return pl.LazyFrame(schema={
                "underlying": pl.Utf8, "trade_date": pl.Date, "expiration": pl.Date,
                "strike_short_call": pl.Float64, "price_short_call": pl.Float64,
                "strike_long_call": pl.Float64, "price_long_call": pl.Float64,
                "strike_short_put": pl.Float64, "price_short_put": pl.Float64,
                "strike_long_put": pl.Float64, "price_long_put": pl.Float64,
                "net_credit": pl.Float64, "strategy_name": pl.Utf8,
            })

        ldf = ldf.join(vc.lazy(), on=GROUP_KEY, how="inner")

        # --- Step 3: Split into calls / puts ---
        calls = ldf.filter(pl.col("option_type") == "CALL")
        puts = ldf.filter(pl.col("option_type") == "PUT")

        # --- Step 4: Rank by DISTINCT strike (1 row per strike after dedup) ---
        # Calls: rank descending → 1 = highest strike (short call), 2 = 2nd highest (long call)
        calls_ranked = calls.with_columns(
            strike_rank=pl.col("strike_price")
                .rank(method="dense", descending=True)
                .over(GROUP_KEY)
        )

        s_c = calls_ranked.filter(pl.col("strike_rank") == 1).select([
            *[pl.col(c) for c in GROUP_KEY],
            pl.col("strike_price").alias("strike_short_call"),
            pl.col("mid_price").alias("price_short_call"),
        ])

        l_c = calls_ranked.filter(pl.col("strike_rank") == 2).select([
            *[pl.col(c) for c in GROUP_KEY],
            pl.col("strike_price").alias("strike_long_call"),
            pl.col("mid_price").alias("price_long_call"),
        ])

        # Puts: rank ascending → 1 = lowest strike (short put), 2 = 2nd lowest (long put)
        puts_ranked = puts.with_columns(
            strike_rank=pl.col("strike_price")
                .rank(method="dense", descending=False)
                .over(GROUP_KEY)
        )

        s_p = puts_ranked.filter(pl.col("strike_rank") == 1).select([
            *[pl.col(c) for c in GROUP_KEY],
            pl.col("strike_price").alias("strike_short_put"),
            pl.col("mid_price").alias("price_short_put"),
        ])

        l_p = puts_ranked.filter(pl.col("strike_rank") == 2).select([
            *[pl.col(c) for c in GROUP_KEY],
            pl.col("strike_price").alias("strike_long_put"),
            pl.col("mid_price").alias("price_long_put"),
        ])

        # --- Step 5: Check 4-leg counts ---
        s_c_df = s_c.collect()
        l_c_df = l_c.collect()
        s_p_df = s_p.collect()
        l_p_df = l_p.collect()
        log.warning(f"LOGIC 4-legs: s_c={len(s_c_df)}, l_c={len(l_c_df)}, s_p={len(s_p_df)}, l_p={len(l_p_df)}")

        # --- Step 6: Join all 4 legs ---
        res = s_c_df.lazy() \
            .join(l_c_df.lazy(), on=GROUP_KEY, how="inner") \
            .join(s_p_df.lazy(), on=GROUP_KEY, how="inner") \
            .join(l_p_df.lazy(), on=GROUP_KEY, how="inner") \
            .select([
                *[pl.col(c) for c in GROUP_KEY],
                pl.col("strike_short_call"), pl.col("price_short_call"),
                pl.col("strike_long_call"),  pl.col("price_long_call"),
                pl.col("strike_short_put"),  pl.col("price_short_put"),
                pl.col("strike_long_put"),   pl.col("price_long_put"),
            ]) \
            .with_columns(
                net_credit=((pl.col("price_short_put") + pl.col("price_short_call"))
                            - (pl.col("price_long_put") + pl.col("price_long_call"))).round(2),
                strategy_name=pl.lit("IRON_CONDOR"),
            ) \
            .rename({"expiry_date": "expiration"})

        final_df = res.collect()
        log.warning(f"LOGIC FINAL: {len(final_df)} iron condor signals")
        if len(final_df) > 0:
            log.warning(f"LOGIC SAMPLE OUTPUT: {final_df.head(3).to_dicts()}")

        return final_df.lazy()

    def generate_signals(self, df: DataFrame) -> DataFrame:
        input_count = df.count()
        logger.info(f"🔍 generate_signals() received {input_count} rows")

        output_schema = (
            "underlying STRING, trade_date DATE, expiration DATE, "
            "strike_short_call DOUBLE, price_short_call DOUBLE, "
            "strike_long_call DOUBLE, price_long_call DOUBLE, "
            "strike_short_put DOUBLE, price_short_put DOUBLE, "
            "strike_long_put DOUBLE, price_long_put DOUBLE, "
            "net_credit DOUBLE, strategy_name STRING"
        )

        filtered_df = df.select(*self.required_columns)

        # ── DRIVER-SIDE DIAGNOSTICS ──
        logger.info("--- DATA DIAGNOSTICS START ---")
        logger.info("Distinct underlying values:")
        filtered_df.select("underlying").distinct().show(truncate=False)

        logger.info("Row counts by option_type:")
        filtered_df.groupBy("option_type").count().show(truncate=False)

        logger.info(f"Schema: {filtered_df.dtypes}")
        logger.info("Sample 5 rows:")
        filtered_df.show(5, truncate=False)

        # Check valid groups using underlying (not symbol)
        calls_df = filtered_df.filter(F.col("option_type") == "CALL")
        puts_df = filtered_df.filter(F.col("option_type") == "PUT")
        logger.info(f"Total CALL rows: {calls_df.count()}, Total PUT rows: {puts_df.count()}")

        call_groups = calls_df.groupBy("underlying", "trade_date", "expiry_date") \
            .agg(F.countDistinct("strike_price").alias("num_calls")) \
            .filter(F.col("num_calls") >= 2)
        put_groups = puts_df.groupBy("underlying", "trade_date", "expiry_date") \
            .agg(F.countDistinct("strike_price").alias("num_puts")) \
            .filter(F.col("num_puts") >= 2)

        valid_groups = call_groups.join(put_groups, on=["underlying", "trade_date", "expiry_date"], how="inner")
        valid_count = valid_groups.count()
        logger.info(f"Valid groups (2+ call strikes AND 2+ put strikes): {valid_count}")

        if valid_count > 0:
            logger.info("Sample valid groups:")
            valid_groups.show(5, truncate=False)

        logger.info("--- DATA DIAGNOSTICS END ---")

        # ── Repartition by group key so each partition has complete groups ──
        grouped_df = filtered_df.repartition(
            F.col("underlying"), F.col("trade_date"), F.col("expiry_date")
        )
        logger.info("Repartitioned by (underlying, trade_date, expiry_date)")

        result = grouped_df.mapInPandas(self._process_partition, schema=output_schema)

        result_count = result.count()
        logger.info(f"✅ Final iron-condor signals: {result_count} rows")

        return result

    def _process_partition(self, pdf_iterator):
        import logging
        import pandas as pd
        log = logging.getLogger("IronCondorStrategy.executor")

        # Concatenate ALL batches in this partition before processing.
        # mapInPandas splits a partition into multiple Arrow batches;
        # we must reassemble them so each (underlying, trade_date, expiry_date)
        # group is complete before running logic().
        batches = [pdf for pdf in pdf_iterator if not pdf.empty]

        if not batches:
            log.info("Partition: no data, skipping")
            return

        full_pdf = pd.concat(batches, ignore_index=True)
        log.info(f"Partition: {len(batches)} batches, {len(full_pdf)} total rows")

        try:
            full_pdf = self.cast_decimals(full_pdf)
            ldf = pl.from_pandas(full_pdf).lazy()
            res = self.logic(ldf)
            result_pdf = res.collect().to_pandas()
            log.info(f"Partition: yielding {len(result_pdf)} iron condor signals")
            yield result_pdf
        except Exception as e:
            log.error(f"Partition error: {type(e).__name__}: {e}", exc_info=True)