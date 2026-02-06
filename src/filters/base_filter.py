from abc import ABC, abstractmethod
from pyspark.sql import DataFrame

class FilterPolicy(ABC):
    @abstractmethod
    def apply(self, df: DataFrame) -> DataFrame:
        """All filters must implement this method"""
        pass
