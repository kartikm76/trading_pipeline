import yaml
import os
from pathlib import Path
from typing import Optional, Any, List

class ConfigManager:
    """
    Finalized Singleton ConfigManager.
    Supports Linear Staging, Medallion Architecture, and Strategy Mapping.
    """
    _instance: Optional['ConfigManager'] = None
    _config: Optional[dict] = None
    _env: str = "dev"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            # Driven by environment variable, default to 'dev' for local testing
            self._env = os.getenv("ENV", "dev").lower()
            self._load_config()

    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_config(self):
        paths_to_check = [
            Path("config.yaml"),
            Path("/app/config.yaml"),
            Path("infrastructure/resources/config.yaml"),
            Path("../config.yaml")
        ]
        config_file = next((p for p in paths_to_check if p.exists()), None)
        if not config_file:
            raise FileNotFoundError("Could not find config.yaml. Check project root.")

        with open(config_file, "r") as f:
            self._config = yaml.safe_load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Recursive getter for nested YAML keys (e.g., 'scaling.bootstrap.max_executors')"""
        keys = key_path.split('.')
        value = self._config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def _get_env_specific(self, key: str, default: Any = None) -> Any:
        """Pulls from top-level 'dev' or 'aws' blocks based on ENV variable."""
        return self.get(f"{self._env}.{key}", default)

    @property
    def env(self) -> str:
        return self._env

    @property
    def environment(self) -> str:
        """Alias for compatibility with SparkSessionBuilder logic."""
        return self._env

    # --- INFRASTRUCTURE & CATALOG ---
    @property
    def warehouse(self) -> str:
        return self._get_env_specific('warehouse')

    @property
    def catalog(self) -> str:
        return self.get('storage.catalog_name')

    @property
    def db_name(self) -> str:
        # Read db_name from environment-specific block, fallback to global storage.db_name
        return self._get_env_specific('db_name', self.get('storage.db_name'))

    @property
    def catalog_impl(self) -> Optional[str]:
        return self._get_env_specific('catalog_impl')

    @property
    def io_impl(self) -> Optional[str]:
        return self._get_env_specific('io_impl')

    @property
    def catalog_type(self) -> str:
        return self._get_env_specific('catalog_type', 'hadoop')

    @property
    def use_location_clause(self) -> bool:
        return self._get_env_specific('use_location_clause', False)

    # --- PATHS (Staging Area Strategy) ---
    @property
    def raw_data_path(self) -> str:
        """Spark reads from the staging directory managed by the batch script."""
        base = self._get_env_specific('raw_base_path')
        return f"{base.rstrip('/')}/staging/"

    # --- METADATA & FORMATS ---
    @property
    def raw_format(self) -> str:
        return self.get('data_format.raw', 'csv')

    @property
    def iceberg_format(self) -> str:
        return self.get('data_format.iceberg', 'parquet')

    @property
    def format_version(self) -> str:
        return str(self._get_env_specific('format_version', '1'))

    @property
    def write_mode(self) -> str:
        return self._get_env_specific('write_mode', 'append')

    def get_table_path(self, stage: str) -> str:
        table_id = self.get(f"storage.tables.{stage}")
        return f"{self.catalog}.{self.db_name}.{table_id}"

    # --- STRATEGIES & FILTERS (Fixed for StrategyFactory) ---
    @property
    def active_strategy_info(self) -> List[dict]:
        """Returns a list of active strategies so Factory can access index [0]."""
        strategies = self.get('strategies', [])
        return [s for s in strategies if s.get('active') == 'Y']

    @property
    def underlying_mapping(self) -> dict:
        """SPX -> SPY mapping for Silver Enrichment."""
        return self.get('underlying_mapping', {})

    @property
    def active_filter_classes(self) -> List[str]:
        filters = self.get('filters', [])
        return [f['class'] for f in filters if f.get('active') == 'Y']

    # --- SCALING ---
    @property
    def batch_size(self) -> int:
        return int(self.get('scaling.batch_size', 15))

    def get_scaling_config(self, mode: str = "daily") -> dict:
        return self.get(f"scaling.{mode}", {})