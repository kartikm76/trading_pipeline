from abc import ABC, abstractmethod
from pyspark.sql import DataFrame, SparkSession

class BaseIngestor(ABC):
    def __init__(self, spark: SparkSession):
        self.spark = spark

    @abstractmethod
    def ingest(self, path: str) -> DataFrame:
        """
        Abstract method to read data from a specific source path.
        Returns a Spark DataFrame.
        """
        pass