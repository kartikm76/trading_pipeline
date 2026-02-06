import yaml
import os
from pathlib import Path
from typing import Optional, Any, List

class ConfigManager:
    """
    Singleton class to manage application configuration.
    Aligned with Medallion architecture and environment-specific scaling.
    """
    _instance: Optional['ConfigManager'] = None
    _config: Optional[dict] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._load_config()

    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_config(self):
        paths_to_check = [
            Path("config.yaml"),
            Path("infrastructure/resources/config.yaml"),
            Path("../../resources/config.yaml")
        ]

        config_file = next((p for p in paths_to_check if p.exists()), None)
        if not config_file:
            raise FileNotFoundError(f"Could not find config.yaml. Checked: {paths_to_check}")

        with open(config_file, "r") as f:
            self._config = yaml.safe_load(f)
        self._apply_env_overrides()

    def _apply_env_overrides(self):
        env_override = os.getenv("ENV")
        if env_override:
            self._config['project']['environment'] = env_override.lower()

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split('.')
        value = self._config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def _get_env_specific(self, key: str, default: Any = None) -> Any:
        # Correctly pulls from top-level 'dev' or 'prod' blocks
        return self.get(f"{self.environment}.{key}", default)

    @property
    def environment(self) -> str:
        return self.get('project.environment', 'dev').lower()

    # --- DATA FORMATS ---
    @property
    def raw_format(self) -> str:
        return self.get('data_format.raw', 'csv')

    @property
    def iceberg_format(self) -> str:
        return self.get('data_format.iceberg', 'parquet')

    # --- STORAGE & TABLES ---
    @property
    def catalog(self) -> str:
        return self.get('storage.catalog_name')

    @property
    def db_name(self) -> str:
        return self.get('storage.db_name')

    def get_table_path(self, stage: str) -> str:
        table_id = self.get(f"storage.tables.{stage}")
        if not table_id:
            raise ValueError(f"Table stage '{stage}' not found in configuration.")
        return f"{self.catalog}.{self.db_name}.{table_id}"

    # --- ENVIRONMENT SPECIFIC PATHS & IMPLS ---
    @property
    def warehouse(self) -> str:
        return self._get_env_specific('warehouse')

    @property
    def path_landing(self) -> str:
        return self._get_env_specific('path_landing')

    @property
    def path_processed(self) -> str:
        return self._get_env_specific('path_processed')

    @property
    def raw_data_path(self) -> str:
        return self._get_env_specific('raw_data_path')

    @property
    def use_location_clause(self) -> bool:
        return self._get_env_specific('use_location_clause', False)

    @property
    def catalog_impl(self) -> Optional[str]:
        return self._get_env_specific('catalog_impl')

    @property
    def catalog_type(self) -> str:
        return self._get_env_specific('catalog_type', 'hadoop')

    @property
    def io_impl(self) -> Optional[str]:
        return self._get_env_specific('io_impl')

    @property
    def write_mode(self) -> str:
        return self._get_env_specific('write_mode', 'append')

    @property
    def format_version(self) -> str:
        return str(self._get_env_specific('format_version', '1'))

    # --- SCALING (Top-level in YAML) ---
    def get_scaling_config(self, mode: str = "bootstrap") -> dict:
        """Corrected: Reads from the top-level scaling block as per your YAML."""
        return self.get(f"scaling.{mode}", {})

    # --- Strategies) ---
    @property
    def active_strategy_info(self) -> list[Any]:
        """
        Returns the config dictionary for the active strategy.
        Example: {'class': 'LaymanSPYStrategy', 'active': 'Y', 'underlying': 'SPY'}
        """
        strategies = self.get('strategies', [])
        return [s for s in strategies if s.get('active') == 'Y']

    # --- FILTERS ---
    @property
    def active_filter_classes(self) -> List[str]:
        filters = self.get('filters', [])
        return [f['class'] for f in filters if f.get('active') == 'Y']

    # --- UNDERLYING MAPPING ---
    @property
    def underlying_mapping(self) -> dict:
        """
        Returns the mapping of option symbols to tradeable underlyings.
        Example: {'SPX': 'SPY', 'NDX': 'QQQ'}
        """
        return self.get('underlying_mapping', {})

    def __repr__(self) -> str:
        return f"<ConfigManager(env='{self.environment}', catalog='{self.catalog}')>"