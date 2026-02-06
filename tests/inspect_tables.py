import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.spark_session import SparkSessionBuilder

# Create Spark session (ConfigManager is handled internally)
spark = SparkSessionBuilder.create()

# Show schema with data types
print("\n=== Silver Table Schema ===")
spark.table("glue_catalog.trading_db.enriched_options_silver").printSchema()

# Show sample data
print("\n=== Sample Data (5 rows) ===")
spark.table("glue_catalog.trading_db.enriched_options_silver").show(5, truncate=False)

# Clean up
SparkSessionBuilder.stop()