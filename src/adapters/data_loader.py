# Define the production schema based on your 1GB sample
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType, IntegerType

PRODUCTION_SCHEMA = StructType([
    StructField("ts_recv", TimestampType(), True),
    StructField("ts_event", TimestampType(), True),
    StructField("rtype", IntegerType(), True),
    StructField("publisher_id", IntegerType(), True),
    StructField("instrument_id", StringType(), True),
    StructField("side", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("size", IntegerType(), True),
    StructField("flags", IntegerType(), True),
    StructField("bid_px_00", DoubleType(), True),
    StructField("ask_px_00", DoubleType(), True),
    StructField("bid_sz_00", IntegerType(), True),
    StructField("ask_sz_00", IntegerType(), True),
    StructField("bid_pb_00", IntegerType(), True),
    StructField("ask_pb_00", IntegerType(), True),
    StructField("symbol", StringType(), True)
])