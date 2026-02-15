import logging
import concurrent.futures
import polars as pl
from strategies.strategy_factory import StrategyFactory

logger = logging.getLogger(__name__)

class StrategyOrchestrator:
    def __init__(self, config, spark):
        self.config = config
        self.spark = spark

    def run(self, strategy_names=None):
        # Load Silver once as the shared source for all strategies
        silver_table = self.config.get_table_path('silver')

        # Pull only strategies marked active: "Y"
        active_info = self.config.active_strategy_info

        # Filter for active strategies from config
        targets = strategy_names or [s['class'] for s in active_info]
        if strategy_names:
            targets = [t for t in targets if t in strategy_names]

        if not targets:
            logger.warning("No active strategies found.")
            return

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as executor:
            futures_dict = {
                executor.submit(self.execute_strategy, name, silver_table): name
                    for name in targets
            }
            for future in concurrent.futures.as_completed(futures_dict):
                name = futures_dict[future]
                try:
                    future.result()
                    logger.info(f"✅ {name} completed successfully.")
                    results[name] = True
                except Exception as e:
                    logger.error(f"❌ {name} failed: {e}", exc_info=True)
                    results[name] = False

        return results

    def execute_strategy(self, name, silver_table):
        # 1. Instantiate via updated Factory
        strategy = StrategyFactory.get_strategy(name, self.config)

        # 2. Distributed processing on EMR (Spark -> Polars -> Spark)
        gold_df = strategy.generate_signals(self.spark.table(silver_table))

        # 3. Write to strategy-specific Gold table using createOrReplace
        # Pattern: trading_db.gold_ironcondorstrategy
        gold_table = f"{self.config.db_name}.gold_{name.lower()}"

        gold_df.writeTo(gold_table) \
            .tableProperty("format-version", "2") \
            .tableProperty("write.format.default", "parquet") \
            .partitionedBy("trade_date") \
            .createOrReplace()




