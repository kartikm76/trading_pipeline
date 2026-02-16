from adapters.adapter_factory import AdapterFactory
from utils.iceberg_setup import IcebergTableManager
from services.silver_enricher import SilverEnricher
import logging

logger = logging.getLogger(__name__)

class DataLoadOrchestrator:
    def __init__(self, config, spark):
        self.config = config
        self.spark = spark
        self.dba = IcebergTableManager(config, spark)
        self.enricher = SilverEnricher(config)

    def run(self, is_bootstrap: bool):
        # --- 1. Infrastructure ---
        self.dba.setup_infrastructure()

        # --- 2. Bronze (Ingestion) ---
        adapter = AdapterFactory.get_adapter(self.config.raw_format, self.spark, self.config)
        raw_df = adapter.ingest(path=self.config.raw_data_path, is_bootstrap=is_bootstrap)

        # --- 3. Silver (Enrichment Delegate) ---
        bronze_table = self.config.get_table_path('bronze')
        bronze_df = self.spark.table(bronze_table)
        silver_df = self.enricher.process(bronze_df)

        silver_table = self.config.get_table_path('silver')
        silver_df.writeTo(silver_table) \
            .tableProperty("format-version", self.config.format_version) \
            .tableProperty("write.format.default", self.config.iceberg_format) \
            .tableProperty("write.update.mode", "merge-on-read") \
            .partitionedBy("trade_date") \
            .createOrReplace()

        logger.info(f"✅ Dataload complete: Bronze + Silver tables created (bootstrap={is_bootstrap})")