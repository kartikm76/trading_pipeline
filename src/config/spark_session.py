from pyspark.sql import SparkSession
from .config_manager import ConfigManager
from typing import Optional

class SparkSessionBuilder:
    """
    Singleton class to manage Spark Session creation and lifecycle.
    Ensures only one Spark session exists throughout the application.
    """
    _instance: Optional[SparkSession] = None

    @classmethod
    def create(cls) -> SparkSession:
        """
        Create or return the existing Spark session.
        Uses ConfigManager to get configuration.
        """
        if cls._instance is None or cls._instance._jsc is None:
            config = ConfigManager.get_instance()
            cls._instance = cls._build_session(config)
        return cls._instance

    @classmethod
    def get_instance(cls) -> Optional[SparkSession]:
        """
        Get the existing Spark session instance without creating a new one.
        """
        return cls._instance

    @classmethod
    def _build_session(cls, config: ConfigManager) -> SparkSession:
        """
        Internal method to build the Spark session with Iceberg configurations.
        """
        # Base configuration
        # src/config/spark_session.py
        catalog_name = config.catalog

        # Base builder
        builder = SparkSession.builder \
            .appName("OptionChain-EMR-Pipeline") \
            .config("spark.sql.codegen.wholeStage", "false") \
            .config("spark.driver.memory", "4g") \
            .config("spark.executor.memory", "4g") \
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
            .config(f"spark.sql.catalog.{catalog_name}", "org.apache.iceberg.spark.SparkCatalog") \
            .config(f"spark.sql.catalog.{catalog_name}.warehouse", config.warehouse)

        if config.environment == 'prod':
            # EMR 7.1.0 Optimized Path
            builder = builder.config("spark.jars", "/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar")
            builder = builder.config(f"spark.sql.catalog.{catalog_name}.catalog-impl", config.catalog_impl)
            builder = builder.config(f"spark.sql.catalog.{catalog_name}.io-impl", config.io_impl)
        else:
            # Local Dev Path - RE-ENABLED AND CORRECTED
            # We use 1.6.1 to match Spark 3.5/Scala 2.12 perfectly
            builder = builder.config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1")
            builder = builder.config(f"spark.sql.catalog.{catalog_name}.type", "hadoop")

        return builder.getOrCreate()

    @classmethod
    def stop(cls):
        """Stops the existing Spark session."""
        if cls._instance is not None:
            cls._instance.stop()
            cls._instance = None

    @classmethod
    def reset(cls):
        """Alias for stop() method. Stops and resets the singleton instance."""
        cls.stop()