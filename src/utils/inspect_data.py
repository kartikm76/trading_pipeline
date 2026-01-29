import pandas as pd
import pyarrow.parquet as pq

PATH = "data/raw/spy_tick_data_50gb.parquet"

def inspect():
    # Only read the first 10 rows
    print(f"Inspecting {PATH}...")
    df_head = pq.read_table(PATH).slice(0, 10).to_pandas()

    print("\n--- First 10 Rows ---")
    print(df_head)

    # Check for nulls in a specific column to ensure data quality
    print("\n--- Data Quality Check ---")
    print(f"Timestamp Range: {df_head['Timestamp'].min()} to {df_head['Timestamp'].max()}")

if __name__ == "__main__":
    inspect()