import os
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

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
        env_key = f"{self._prefix}{key}" if self._prefix else key
        value = os.getenv(env_key, default)
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
            if not key.startswith("_"):
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