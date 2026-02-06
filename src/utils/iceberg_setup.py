class IcebergTableManager:
    def __init__(self, config, spark):
        self.config = config
        self.spark = spark
        self.db_prefix = f"{self.config.catalog}.{self.config.db_name}"

    def setup_infrastructure(self) -> None:
        catalog = self.config.catalog
        db = self.config.db_name
        self.spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {catalog}.{db}")

    def materialize_view(self, source_table: str, target_table: str, criteria: str) -> None:
        """
        ONE method to rule them all.
        The 'CREATE OR REPLACE' boilerplate lives ONLY here.
        """
        source = f"{self.db_prefix}.{source_table}"
        target = f"{self.db_prefix}.{target_table}"

        print(f"--- [Infrastructure] Materializing {target} using criteria: {criteria} ---")

        self.spark.sql(f"""
            CREATE OR REPLACE TABLE {target} AS
            SELECT * FROM {source}
            WHERE {criteria}
        """)