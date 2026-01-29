import yaml
import os
from pathlib import Path
from typing import Optional, Any

class ConfigManager:
    """
    Singleton class to manage application configuration.
    Reads config.yaml once and provides centralized access throughout the application.
    """
    _instance: Optional['ConfigManager'] = None
    _config: Optional[dict] = None

    def __new__(cls):
        """Ensure only one instance of ConfigManager exists."""
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the ConfigManager and load configuration if not already loaded."""
        if self._config is None:
            self._load_config()

    def _load_config(self):
        # 1. Look in the current working directory (Cloud/EMR behavior)
        config_file = Path("config.yaml")

        # 2. If not found, fall back to relative path (Local Mac behavior)
        if not config_file.exists():
            config_file = "../../resources/config.yaml"

        if not config_file.exists():
            raise FileNotFoundError(f"Could not find config.yaml at {config_file.absolute()}")

        with open(config_file, "r") as f:
            self._config = yaml.safe_load(f)

        # Apply environment variable overrides
        self._apply_env_overrides()
        print(f"Configuration loaded from {config_file}")

    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Override environment from ENV variable if set
        env_override = os.getenv("ENV")
        if env_override:
            self._config['project']['environment'] = env_override.lower()

        # Security: Always check for API Key in environment first
        api_key_env = os.getenv("POLYGON_API_KEY")
        if api_key_env:
            self._config['polygon']['api_key'] = api_key_env

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
        # Internal helper to pull from storage.{dev/prod}.key
        return self.get(f"storage.{self.environment}.{key}", default)

    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        """Get the existing ConfigManager instance without creating a new one."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def environment(self) -> str:
        return self.get('project.environment', 'dev').lower()

    @property
    def raw_data_path(self) -> str:
        return self._get_env_specific('raw_data_path')

    @property
    def data_format(self) -> str:
        return self._get_env_specific('data_format', 'csv')

    @property
    def catalog(self) -> str:
        return self.get('storage.catalog_name')

    @property
    def db_name(self) -> str:
        return self.get('storage.db_name')

    @property
    def table_name(self) -> str:
        return self.get('storage.table_name')

    @property
    def use_location_clause(self) -> bool:
        """Determines if the CREATE TABLE should include an explicit LOCATION."""
        return self._get_env_specific('use_location_clause', False)

    @property
    def warehouse(self) -> str:
        """Returns the base warehouse path (local dir or S3 URI)."""
        return self._get_env_specific('warehouse')

    def reload(self):
        """Reload configuration from YAML file."""
        self._config = None
        self._load_config()

    @classmethod
    def reset(cls):
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
        cls._config = None

    def __repr__(self) -> str:
        """String representation of ConfigManager."""
        return f"<ConfigManager(config_path='{self._config}', environment='{self.environment}')>"