import streamlit as st
from src.config import ConfigManager, SparkSessionBuilder

st.set_page_config(page_title="Trading Universe Manager", layout="wide")

def main():
    st.title("🛡️ Iceberg Control Center")
    st.subheader("Manage Ticker Universe")

    # 1. Initialize Spark & Config
    config = ConfigManager.get_instance()
    spark = SparkSessionBuilder.create()
    table_path = f"{config.catalog}.{config.db_name}.ticker_universe"

    #2. Sidebar: Add New Ticker
    with st.sidebar:
        st.header("Add to Universe")
        new_symbol = st.text_input("Symbol (e.g., AAPL)").upper()
        target_delta = st.number_input("Target Delta", value=-0.10, step=0.01)
        if st.button("Add Ticker"):
            if new_symbol:
                spark.sql(f"""
                    INSERT INTO {table_path} 
                    VALUES ('{new_symbol}', {target_delta}, true, CURRENT_TIMESTAMP())
                """)
                st.success(f"✓ Added {new_symbol} to ticker universe")
            else:
                st.error("Please enter a ticker symbol.")

    # 3. Main Area: View Universe
    st.write("### Active Tickers")
    try:
        ticker_universe_df = spark.table(table_path).toPandas()
        if not ticker_universe_df.empty:
            st.dataframe(ticker_universe_df, use_container_width=True)

            #Simple Delete Logic
            to_delete = st.selectbox("Select Ticker to Delete", ticker_universe_df["symbol"])
            if st.button("Delete Ticker"):
                spark.sql(f"""
                    DELETE FROM {table_path}
                    WHERE symbol = '{to_delete}'
                """)
                st.success(f"✓ Deleted {to_delete} from ticker universe")
        else:
            st.warning("No tickers in universe")
    except Exception as e:
        st.error(f"Error reading Iceberg table: {e}")

if __name__ == "__main__":
    main()