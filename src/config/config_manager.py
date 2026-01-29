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
    _config_path = os.path.join(os.getcwd(), "config.yaml")
    if not os.path.exists(_config_path):
        # Fallback to your local project structure path
        _config_path = os.path.join(os.path.dirname(__file__), "../../resources/config.yaml")

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
            project_root = Path(__file__).parent.parent.parent
            config_file = project_root / "resources" / "config.yaml"

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
            self._config['environment'] = env_override

        # Override API key from environment if available
        if 'polygon' in self._config:
            api_key_env = os.getenv("POLYGON_API_KEY") or os.getenv("API_KEY")
            if api_key_env:
                self._config['polygon']['api_key'] = api_key_env

    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        """Get the existing ConfigManager instance without creating a new one."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        Args:
            key_path: Dot-separated path to the config value (e.g., 'polygon.api_key')
            default: Default value if key is not found
        Returns:
            The configuration value or default if not found
        """
        keys = key_path.split('.')
        value = self._config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def get_env_config(self, key: str, default: Any = None) -> Any:
        """
        Get environment-specific configuration.
        Args:
            key: Configuration key within the environment section
            default: Default value if not found

        Returns:
            Environment-specific configuration value
        """
        env = self.environment.lower()
        return self.get(f'storage.{env}.{key}', default)

    def get_all(self) -> dict:
        """Get the entire configuration dictionary."""
        return self._config.copy()

    def get_section(self, section: str) -> dict:
        """Get an entire configuration section."""
        return self._config.get(section, {}).copy()

    @property
    def environment(self) -> str:
        """Get environment (DEV or PROD)."""
        return self.get('environment', 'DEV')

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.upper() == 'PROD'

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.upper() == 'DEV'

    @property
    def raw_data_path(self) -> str:
        """Get raw data path based on environment."""
        return self.get_env_config('raw_data_path')

    @property
    def api_key(self) -> str:
        """Get API key from config."""
        return self.get('polygon.api_key')

    @property
    def api_base_url(self) -> str:
        """Get API base URL from config."""
        return self.get('polygon.base_url')

    @property
    def warehouse(self) -> str:
        """Get warehouse path based on environment."""
        return self.get_env_config('warehouse')

    @property
    def db_name(self) -> str:
        """Get database name from config."""
        return self.get('storage.db_name')

    @property
    def catalog(self) -> str:
        """Get catalog name from config."""
        return self.get('storage.catalog_name', 'glue_catalog')

    @property
    def catalog_type(self) -> Optional[str]:
        """Get catalog type (only for dev/hadoop catalogs)."""
        return self.get_env_config('catalog_type')

    @property
    def catalog_impl(self) -> Optional[str]:
        """Get catalog implementation (only for prod/glue catalogs)."""
        return self.get_env_config('catalog_impl')

    @property
    def io_impl(self) -> Optional[str]:
        """Get IO implementation (only for prod)."""
        return self.get_env_config('io_impl')

    @property
    def target_delta(self) -> float:
        """Get target delta for strategy."""
        return self.get('strategy.target_delta')

    @property
    def use_location_clause(self) -> bool:
        """Determine if LOCATION clause should be used in CREATE TABLE."""
        return self.is_production

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
        return f"<ConfigManager(config_path='{self._config_path}', environment='{self.environment}')>"