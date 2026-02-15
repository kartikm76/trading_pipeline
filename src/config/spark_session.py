import os

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
        # --- 1. COMMON CONFIG (All Environments) ---
        builder = SparkSession.builder \
            .appName("OptionChain-EMR-Pipeline") \
            .config("spark.sql.codegen.wholeStage", "false") \
            .config("spark.driver.memory", "4g") \
            .config("spark.executor.memory", "4g") \
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
            .config(f"spark.sql.catalog.{catalog_name}", "org.apache.iceberg.spark.SparkCatalog") \
            .config(f"spark.sql.catalog.{catalog_name}.warehouse", config.warehouse)

        # --- 2. ENVIRONMENT SPECIFIC CONFIG ---
        if config.environment == 'aws':
            # AWS path: EMR Serverless uses pre-installed JARs,
            # local Mac downloads the AWS SDK to speak to Glue/S3
            is_emr = os.path.exists("/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar")

            if is_emr:
                builder = builder.config("spark.jars", "/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar")
            else:
                # Local Mac -> AWS Glue/S3: download JARs via Maven
                builder = builder.config("spark.jars.packages",
                                         "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1,"
                                         "software.amazon.awssdk:bundle:2.20.160,"
                                         "software.amazon.awssdk:url-connection-client:2.20.160")
                builder = builder.config("spark.hadoop.fs.s3a.aws.credentials.provider",
                                         "com.amazonaws.auth.DefaultAWSCredentialsProviderChain")

            builder = builder.config(f"spark.sql.catalog.{catalog_name}.catalog-impl", config.catalog_impl)
            builder = builder.config(f"spark.sql.catalog.{catalog_name}.io-impl", config.io_impl)

        elif config.environment == 'local':
            # Local PC -> Local Files: Pure sandbox mode using Hadoop catalog
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