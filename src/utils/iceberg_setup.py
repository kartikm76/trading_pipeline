class IcebergTableManager:
    def __init__(self, spark, config):
        self.spark = spark
        self.config = config
        self.db_prefix = f"{self.config.catalog}.{self.config.db_name}"

    def setup_infrastructure(self) -> None:
        self.spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {self.db_prefix}")

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