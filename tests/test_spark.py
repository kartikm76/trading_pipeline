import os
import sys
from config.spark_session import SparkSessionBuilder

def run_lock_test():
    # 1. Initialize Hybrid Spark Session
    # This will download AWS JARs and connect to Glue/S3
    print("Initializing Hybrid Spark Session (Local Mac -> AWS Glue)...")
    try:
        spark = SparkSessionBuilder.create()
    except Exception as e:
        print(f"Failed to initialize Spark: {e}")
        sys.exit(1)

    test_table = "glue_catalog.trading_db.test_lock_table"

    # 2. Setup Phase: Create and Populate
    print(f" Step 1: Creating {test_table} in AWS...")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {test_table} (id INT, status STRING) USING iceberg")
    spark.sql(f"INSERT INTO {test_table} VALUES (1, 'active')")

    print("Table created and data inserted. Verification read:")
    spark.table(test_table).show()

    # --- STOP ---
    input("\n ACTION REQUIRED: Go to AWS Glue Console and apply the DENY policy now. Press Enter once applied...")

    # 3. Destruction Phase: The "Hard Lock" Test
    print(f"\n Step 2: Attempting to DROP {test_table} from IntelliJ...")
    try:
        spark.sql(f"DROP TABLE {test_table}")
        print("FAIL: Table was dropped! The Glue Resource Policy is NOT working.")
    except Exception as e:
        # We look for the AccessDeniedException from the Glue Service
        error_msg = str(e)
        if "AccessDeniedException" in error_msg or "explicit deny" in error_msg:
            print("---" * 10)
            print("TEST SUCCESSFUL: THE LOCK IS ACTIVE")
            print("The AWS Glue Service blocked the drop request with an explicit deny.")
            print("---" * 10)
        else:
            print(f"Unexpected error during drop: {e}")

if __name__ == "__main__":
    run_lock_test()