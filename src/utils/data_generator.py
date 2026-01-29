import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pyarrow as pa
import pyarrow.parquet as pq

# baseline data location
INPUT_SAMPLE = "data/raw/SPY_option_chain.csv"

# where the 50GB monster will live
OUTPUT_PATH = "data/raw/spy_tick_data_50gb.parquet"

def generate_50gb_dataset(base_df: pd.DataFrame, output_path, target_rows=430_000_000):
    """
    Generates ~430M rows (~50GB raw CSV equivalent)
    using vectorized bootstrapping.
    """
    # Define the PyArrow schema based on your file
    schema = pa.schema([
        ('Timestamp', pa.timestamp('us')),
        ('Trade Date', pa.string()),
        ('Strike', pa.float64()),
        ('Expiry Date', pa.string()),
        ('Call/Put', pa.string()),
        ('Last Trade Price', pa.float64()),
        ('Bid Price', pa.float64()),
        ('Ask Price', pa.float64()),
        ('Bid Implied Volatility', pa.float64()),
        ('Ask Implied Volatility', pa.float64()),
        ('Open Interest', pa.int64()),
        ('Volume', pa.int64()),
        ('Delta', pa.float64()),
        ('Gamma', pa.float64()),
        ('Vega', pa.float64()),
        ('Theta', pa.float64()),
        ('Rho', pa.float64())
    ])

    writer = pq.ParquetWriter(output_path, schema, compression='snappy')

    chunk_size = 1_000_000
    num_chunks = target_rows // chunk_size
    current_time = datetime(2026, 1, 1, 9, 30)

    print(f"Starting generation of {target_rows} rows...")

    for i in range(num_chunks):
        # 1. Fast bootstrap from sample
        indices = np.random.randint(0, len(base_df), chunk_size)
        batch_df = base_df.iloc[indices].copy()

        # 2. Add realistic tick time-spacing (1ms to 50ms gaps)
        deltas = np.cumsum(np.random.randint(1000, 50000, chunk_size))
        batch_df.insert(0, 'Timestamp', [current_time + timedelta(microseconds=int(d)) for d in deltas])
        current_time = current_time + timedelta(microseconds=int(deltas[-1]))

        # 3. Add price noise (volatility)
        noise = np.random.normal(0, 0.005, chunk_size)
        batch_df['Last Trade Price'] = (batch_df['Last Trade Price'] * (1 + noise)).round(2)

        # 4. Convert to Arrow and Write
        table = pa.Table.from_pandas(batch_df, schema=schema)
        writer.write_table(table)

        if i % 10 == 0:
            print(f"Progress: {((i/num_chunks)*100):.1f}% | Rows: {i*chunk_size}")

    writer.close()
    print("Generation Complete.")

# To run: generate_50gb_dataset('spy_tick_data_50gb.parquet')
def main():
    # Load your sample as the base template
    base_df = pd.read_csv(INPUT_SAMPLE)
    generate_50gb_dataset(base_df, OUTPUT_PATH)

if __name__ == "__main__":
    main()