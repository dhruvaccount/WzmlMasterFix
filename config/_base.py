import os
import logging
from typing import Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("wzml.config")


class ConfigError(Exception):
    pass


@dataclass
class BaseConfig:
    _prefix: str = ""
    _group_name: str = "base"

    def __post_init__(self):
        self._loaded = False

    def _get_env(self, key: str, default: Any = None, value_type: type = None) -> Any:
        current_value = getattr(self, key, None)
        use_default = current_value if current_value is not None else default
        prefix = self.__class__._prefix if hasattr(self.__class__, "_prefix") else ""
        env_key = f"{prefix}{key}" if prefix else key
        value = os.getenv(env_key)
        if value is None:
            value = use_default
        if value is None:
            return default
        if value_type and value and value_type != str:
            try:
                if value_type == bool:
                    return str(value).lower() in ("true", "1", "yes")
                elif value_type == int:
                    return int(value)
                elif value_type == float:
                    return float(value)
                elif value_type == list:
                    return [x.strip() for x in str(value).split(",") if x.strip()]
                elif value_type == dict:
                    result = {}
                    for item in str(value).split(","):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            result[k.strip()] = v.strip()
                    return result
            except (ValueError, TypeError):
                return default
        return value

    def _load_from_attrs(self, attrs: dict):
        for key, value in attrs.items():
            if not key.startswith("_") and key not in ("_prefix", "_group_name"):
                setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def set(self, key: str, value: Any):
        setattr(self, key, value)

    def to_dict(self) -> dict:
        return {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_") and not callable(v)
        }

    def reload(self):
        self._loaded = False
        self.load()

    def load(self):
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.to_dict()}>"


__all__ = ["BaseConfig", "ConfigError"]
