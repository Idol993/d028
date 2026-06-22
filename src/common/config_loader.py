import os
import yaml
from pathlib import Path
from typing import Any, Dict


class ConfigLoader:
    _instance = None
    _config: Dict[str, Any] = None

    def __new__(cls, config_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(config_path)
        return cls._instance

    def _load_config(self, config_path: str = None):
        if config_path is None:
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "config" / "system_config.yaml"

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        self._config = self._resolve_env_vars(raw_config)

    def _resolve_env_vars(self, config: Any) -> Any:
        if isinstance(config, dict):
            return {k: self._resolve_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._resolve_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
            env_var = config[2:-1]
            return os.environ.get(env_var, config)
        return config

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @property
    def all_config(self) -> Dict[str, Any]:
        return self._config
