from src.config import SparkSessionBuilder, ConfigManager
from pyspark.sql import SparkSession
from typing import Optional


class IcebergTableManager:
    """
    Manager class for setting up and managing Iceberg tables.
    """

    def __init__(self, spark: Optional[SparkSession] = None,
                 config: Optional[ConfigManager] = None):
        """
        Initialize the IcebergTableManager.

        Args:
            spark: SparkSession instance (if None, will use singleton)
            config: ConfigManager instance (if None, will use singleton)
        """
        self.spark = spark or SparkSessionBuilder.get_instance()
        self.config = config or ConfigManager.get_instance()

        if self.spark is None:
            raise ValueError("SparkSession not initialized. Call SparkSessionBuilder.create() first.")

    def create_database(self, db_name: Optional[str] = None) -> None:
        """
        Create the database/namespace if it doesn't exist.

        Args:
            db_name: Database name (defaults to config.db_name)
        """
        db_name = db_name or self.config.db_name
        self.spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {self.config.catalog}.{db_name}")
        print(f"✓ Created namespace: {self.config.catalog}.{db_name}")

    def create_ticker_universe_table(self, db_name: Optional[str] = None) -> None:
        """
        Create the ticker_universe table.

        Args:
            db_name: Database name (defaults to config.db_name)
        """
        db_name = db_name or self.config.db_name

        # Build the CREATE TABLE statement
        location_clause = ""
        if self.config.use_location_clause:
            location_clause = f"LOCATION '{self.config.warehouse}/{db_name}/ticker_universe'"

        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self.config.catalog}.{db_name}.ticker_universe (                
                symbol STRING,
                target_delta DOUBLE,
                is_active BOOLEAN,
                last_updated TIMESTAMP
            )
            USING iceberg
            {location_clause}
        """)

        print(f"✓ Created table: {self.config.catalog}.{db_name}.ticker_universe")

    def seed_ticker_universe(self, db_name: Optional[str] = None) -> None:
        """
        Seed the ticker_universe table with initial data (SPY).

        Args:
            db_name: Database name (defaults to config.db_name)
        """
        db_name = db_name or self.config.db_name

        exists = self.spark.sql(f"""
            SELECT * 
            FROM {self.config.catalog}.{db_name}.ticker_universe 
            WHERE symbol = 'SPY'
        """).count()

        if exists == 0:
            self.spark.sql(f"""
                INSERT INTO {self.config.catalog}.{db_name}.ticker_universe 
                VALUES ('SPY', {self.config.target_delta}, true, CURRENT_TIMESTAMP())
            """)
            print(f"✓ Seeded ticker universe with SPY (target_delta={self.config.target_delta})")
        else:
            print("✓ SPY already exists in ticker universe")

    def setup_table_infrastructure(self, db_name: Optional[str] = None) -> None:
        """
        Setup all Iceberg tables (database, tables, and seed data).

        Args:
            db_name: Database name (defaults to config.db_name)
        """
        db_name = db_name or self.config.db_name

        print(f"Setting up Iceberg tables in {self.config.environment} environment...")
        print(f"Catalog: {self.config.catalog}")
        print(f"Warehouse: {self.config.warehouse}")
        print("-" * 60)

        self.create_database(db_name)
        self.create_ticker_universe_table(db_name)
        self.seed_ticker_universe(db_name)

        print("-" * 60)
        print("✓ All Iceberg tables setup complete!")


if __name__ == "__main__":
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()

    table_manager = IcebergTableManager(spark=spark, config=config)
    table_manager.setup_table_infrastructure()

    SparkSessionBuilder.stop()