import requests
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
from src.adapters.base_adapter import BaseAdapter

class PolygonAdapter(BaseAdapter):
    def __init__(self, api_key: str, spark: SparkSession):
        self.api_key = api_key
        self.spark = spark
        self.base_url = "https://api.polygon.io"

    def get_options_data(self, ticker: str, start_date: str, end_date: str) -> DataFrame:
        """
        Fetches daily aggregates for a given options ticker.
        Note: For the 'Basic' package, we focus on daily/minute bars.
        """
        url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}?apiKey={self.api_key}"
        response = requests.get(url).json()

        if "results" not in response:
            return self.spark.createDataFrame([], self._get_schema())
        data = response["results"]

        #2. Map Polygon fields to Standard Schema
        data = [
            (
                str(row['t']),      # Convert int timestamp to StringType
                ticker,             # symbol (StringType)
                float(row['c']),    # last_price (DoubleType)
                float(row['v']),    # volume (DoubleType) - THIS IS THE FIX
                # Note: Strike/Expiry/Underlying would be parsed from the ticker string or
                # a separate 'Snapshot' call in a full implementation.
            )
            for row in response.get('results', []) # .get avoids the crash if results are missing
        ]
        return self.spark.createDataFrame(data, self._get_schema())

    def _get_schema(self) -> StructType:
        return StructType([
            StructField("timestamp", StringType(), True),
            StructField("symbol", StringType(), True),
            StructField("close", DoubleType(), True),
            StructField("volume", DoubleType(), True),
        ])