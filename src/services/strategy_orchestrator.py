import logging
import concurrent.futures
import subprocess
from datetime import datetime, timedelta
import polars as pl
from pyspark.sql import functions as F
from strategies.strategy_factory import StrategyFactory

logger = logging.getLogger(__name__)

class StrategyOrchestrator:
    def __init__(self, config, spark):
        self.config = config
        self.spark = spark

    def run(self, strategy_names=None, mode=None, start_date=None, end_date=None):
        """
        Execute strategies based on batch_mode (snapshot/lookback/full).

        Args:
            strategy_names: List of strategy classes to run (optional)
            mode: Force specific batch mode ("snapshot", "lookback", "full") - overrides config
            start_date: Process only this date range (optional, string "YYYY-MM-DD")
            end_date: Process only this date range (optional, string "YYYY-MM-DD")
        """
        silver_table = self.config.get_table_path('silver')
        strategies_config = self.config.get('strategies', {})

        # Convert date strings to datetime objects if provided
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        results = {}

        # Execute snapshot strategies (monthly batching, parallel)
        if self._should_run_mode('snapshot', mode):
            snapshot_strategies = strategies_config.get('snapshot', [])
            active_snapshot = [s for s in snapshot_strategies if s.get('active') == 'Y']
            if active_snapshot:
                logger.info("🔄 Executing SNAPSHOT strategies (monthly batching, parallel)...")
                snapshot_results = self._execute_snapshot_strategies(active_snapshot, silver_table,
                                                                     start_date, end_date)
                results.update(snapshot_results)

        # Execute lookback strategies (sliding windows, sequential)
        if self._should_run_mode('lookback', mode):
            lookback_strategies = strategies_config.get('lookback', [])
            active_lookback = [s for s in lookback_strategies if s.get('active') == 'Y']
            if active_lookback:
                logger.info("🔄 Executing LOOKBACK strategies (sliding windows, sequential)...")
                lookback_results = self._execute_lookback_strategies(active_lookback, silver_table)
                results.update(lookback_results)

        # Execute full strategies (single large job)
        if self._should_run_mode('full', mode):
            full_strategies = strategies_config.get('full', [])
            active_full = [s for s in full_strategies if s.get('active') == 'Y']
            if active_full:
                logger.info("🔄 Executing FULL strategies (single job, entire dataset)...")
                full_results = self._execute_full_strategies(active_full, silver_table)
                results.update(full_results)

        if not results:
            logger.warning("⚠️ No active strategies found in any mode.")

        return results

    def _should_run_mode(self, mode, forced_mode):
        """Check if mode should run."""
        if forced_mode:
            return mode == forced_mode
        return True  # Run all modes by default

    def _execute_snapshot_strategies(self, strategies, silver_table, start_date=None, end_date=None):
        """
        Execute snapshot strategies with monthly batching (parallel).

        If start_date and end_date are provided, process only that single batch.
        Otherwise, generate 12 monthly batches for the entire date range.
        """
        results = {}
        full_silver = self.spark.table(silver_table)

        # If specific date range provided, process only that batch
        if start_date and end_date:
            logger.info(f"🎯 Processing single batch: {start_date} to {end_date}")
            batches = [(start_date, end_date)]
        else:
            # Get date range from data and generate monthly batches
            min_date_row = full_silver.select(F.min("trade_date")).first()
            max_date_row = full_silver.select(F.max("trade_date")).first()
            min_date = min_date_row[0]
            max_date = max_date_row[0]

            logger.info(f"📅 Snapshot date range: {min_date} to {max_date}")

            # Generate monthly batches
            batches = self._generate_monthly_batches(min_date, max_date)
            logger.info(f"📦 Generated {len(batches)} monthly batches")

        # Submit all batches in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for batch_idx, (start_date, end_date) in enumerate(batches):
                for strategy in strategies:
                    strategy_name = strategy['class']
                    batch_key = f"{strategy_name}_batch_{batch_idx+1}"

                    future = executor.submit(
                        self._execute_strategy_batch,
                        strategy_name,
                        strategy,
                        silver_table,
                        start_date,
                        end_date
                    )
                    futures[future] = batch_key

            # Collect results
            for future in concurrent.futures.as_completed(futures):
                batch_key = futures[future]
                try:
                    strategy_name, batch_num = batch_key.rsplit('_batch_', 1)
                    if strategy_name not in results:
                        results[strategy_name] = True
                    future.result()
                    logger.info(f"✅ {batch_key} completed")
                except Exception as e:
                    strategy_name = batch_key.split('_batch_')[0]
                    results[strategy_name] = False
                    logger.error(f"❌ {batch_key} failed: {e}", exc_info=True)

        return results

    def _execute_lookback_strategies(self, strategies, silver_table):
        """
        Execute lookback strategies with sliding windows (sequential).
        Each batch includes lookback_days of prior data for context.
        """
        results = {}
        full_silver = self.spark.table(silver_table)

        min_date_row = full_silver.select(F.min("trade_date")).first()
        max_date_row = full_silver.select(F.max("trade_date")).first()
        min_date = min_date_row[0]
        max_date = max_date_row[0]

        logger.info(f"📅 Lookback date range: {min_date} to {max_date}")

        # Generate monthly batches with lookback buffer
        batches = self._generate_monthly_batches(min_date, max_date)

        for batch_idx, (start_date, end_date) in enumerate(batches):
            for strategy in strategies:
                strategy_name = strategy['class']
                lookback_days = strategy.get('lookback_days', 5)

                # Include lookback buffer
                buffer_start = start_date - timedelta(days=lookback_days)
                buffer_start = max(buffer_start, min_date)  # Don't go before data start

                logger.info(f"🔄 {strategy_name} batch {batch_idx+1}: "
                           f"input {buffer_start} to {end_date}, "
                           f"output {start_date} to {end_date}")

                try:
                    self._execute_strategy_batch(
                        strategy_name,
                        strategy,
                        silver_table,
                        buffer_start,  # Input includes buffer
                        end_date,
                        output_start_date=start_date  # Output only non-overlapping
                    )
                    if strategy_name not in results:
                        results[strategy_name] = True
                    logger.info(f"✅ {strategy_name} batch {batch_idx+1} completed")
                except Exception as e:
                    results[strategy_name] = False
                    logger.error(f"❌ {strategy_name} batch {batch_idx+1} failed: {e}", exc_info=True)

        return results

    def _execute_full_strategies(self, strategies, silver_table):
        """
        Execute full strategies with entire dataset (single large job).
        Uses enhanced resources.
        """
        results = {}

        logger.info("📊 Running FULL dataset analysis (all 2.5B rows)...")

        for strategy in strategies:
            strategy_name = strategy['class']
            try:
                self._execute_strategy_batch(
                    strategy_name,
                    strategy,
                    silver_table,
                    start_date=None,  # Entire dataset
                    end_date=None
                )
                results[strategy_name] = True
                logger.info(f"✅ {strategy_name} (full) completed")
            except Exception as e:
                results[strategy_name] = False
                logger.error(f"❌ {strategy_name} (full) failed: {e}", exc_info=True)

        return results

    def _execute_strategy_batch(self, strategy_name, strategy_config, silver_table,
                               start_date, end_date, output_start_date=None):
        """
        Execute a single strategy batch.

        Args:
            strategy_name: Class name (e.g., "IronCondorStrategy")
            strategy_config: Strategy config dict from config.yaml
            silver_table: Iceberg table name
            start_date: Data range start (datetime)
            end_date: Data range end (datetime)
            output_start_date: For lookback mode, filter output to dates >= this (non_overlapping)
        """
        logger.info(f"🚀 {strategy_name}: Loading data {start_date} - {end_date}")

        # 1. Instantiate strategy
        strategy = StrategyFactory.get_strategy(strategy_name, self.config)

        # 2. Filter silver data
        full_silver = self.spark.table(silver_table)

        if start_date and end_date:
            silver_df = full_silver.filter(
                (F.col("trade_date") >= start_date) &
                (F.col("trade_date") < end_date)
            )
            row_count = silver_df.count()
            logger.info(f"📊 {strategy_name}: {row_count:,} rows for date range {start_date} - {end_date}")
        else:
            # Full dataset
            silver_df = full_silver
            row_count = silver_df.count()
            logger.info(f"📊 {strategy_name}: {row_count:,} rows (full dataset)")

        # 3. Generate signals
        gold_df = strategy.generate_signals(silver_df)

        # 4. Apply non_overlapping filter (for lookback batches)
        output_mode = strategy_config.get('output_mode', 'non_overlapping')
        if output_mode == 'non_overlapping' and output_start_date:
            logger.info(f"🔍 {strategy_name}: Filtering to non-overlapping dates >= {output_start_date}")
            gold_df = gold_df.filter(F.col("trade_date") >= output_start_date)

        # 5. Write to gold table
        gold_table = f"{self.config.catalog}.{self.config.db_name}.gold_{strategy_name.lower()}"

        # Check if table exists
        table_exists = False
        try:
            self.spark.table(gold_table)
            table_exists = True
        except:
            table_exists = False

        if table_exists:
            logger.info(f"📝 {strategy_name}: Appending to {gold_table}")
            gold_df.writeTo(gold_table).append()
        else:
            logger.info(f"📝 {strategy_name}: Creating {gold_table}")
            gold_df.writeTo(gold_table) \
                .tableProperty("format-version", "2") \
                .tableProperty("write.format.default", "parquet") \
                .partitionedBy("trade_date") \
                .create()

        logger.info(f"✅ {strategy_name}: Written to {gold_table}")

    def _generate_monthly_batches(self, min_date, max_date):
        """
        Generate monthly batch tuples: [(2025-01-01, 2025-02-01), (2025-02-01, 2025-03-01), ...]
        """
        batches = []
        current = min_date.replace(day=1)  # Start of month

        while current <= max_date:
            # Next month's first day
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1)
            else:
                next_month = current.replace(month=current.month + 1)

            batches.append((current, next_month))
            current = next_month

        return batches




