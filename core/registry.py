from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable

from core.exceptions import (
    PluginNotFoundError,
    PluginLoadError,
    PluginExecutionError,
    PluginValidationError,
)


class PluginType(StrEnum):
    DOWNLOADER = "downloader"
    UPLOADER = "uploader"
    PROCESSOR = "processor"
    UTILITY = "utility"


class PluginState(StrEnum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class PluginMetadata:
    name: str
    version: str = "1.0.0"
    author: str = "Unknown"
    description: str = ""
    plugin_type: PluginType = PluginType.DOWNLOADER
    dependencies: list[str] = field(default_factory=list)
    config_schema: dict = field(default_factory=dict)


@dataclass
class PluginInfo:
    metadata: PluginMetadata
    state: PluginState = PluginState.UNLOADED
    loaded_at: datetime | None = None
    error: str | None = None
    instance: Any = None


class PluginRegistry:
    _plugins: dict[str, PluginInfo] = {}
    _handlers: dict[str, Callable] = {}
    _event_handlers: dict[str, list[Callable]] = {
        "plugin.loaded": [],
        "plugin.unloaded": [],
        "plugin.error": [],
    }

    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = plugins_dir

    def register_plugin(
        self,
        name: str,
        metadata: PluginMetadata,
        instance: Any,
    ) -> None:
        info = PluginInfo(
            metadata=metadata,
            state=PluginState.LOADED,
            loaded_at=datetime.now(),
            instance=instance,
        )
        self._plugins[name] = info
        self._trigger_event("plugin.loaded", name)

    def unregister_plugin(self, name: str) -> None:
        if name in self._plugins:
            del self._plugins[name]
            self._trigger_event("plugin.unloaded", name)

    def get_plugin(self, name: str) -> Any:
        info = self._plugins.get(name)
        if not info or info.state != PluginState.LOADED:
            raise PluginNotFoundError(name)
        return info.instance

    def get_plugin_info(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

    def list_plugins(self, plugin_type: PluginType | None = None) -> list[str]:
        names = []
        for name, info in self._plugins.items():
            if plugin_type is None or info.metadata.plugin_type == plugin_type:
                names.append(name)
        return sorted(names)

    def list_plugins_by_state(self, state: PluginState) -> list[str]:
        return [name for name, info in self._plugins.items() if info.state == state]

    def plugin_exists(self, name: str) -> bool:
        info = self._plugins.get(name)
        return info is not None and info.state == PluginState.LOADED

    def register_handler(self, action: str, handler: Callable) -> None:
        self._handlers[action] = handler

    def get_handler(self, action: str) -> Callable | None:
        return self._handlers.get(action)

    def on(self, event: str, handler: Callable) -> None:
        if event in self._event_handlers:
            self._event_handlers[event].append(handler)

    def _trigger_event(self, event: str, *args: Any) -> None:
        for handler in self._event_handlers.get(event, []):
            try:
                handler(*args)
            except Exception as e:
                print(f"Event handler error: {e}")

    async def load_plugin_dynamic(
        self,
        name: str,
        metadata: PluginMetadata,
        module: Any,
    ) -> Any:
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "name")
                and attr_name.endswith("Plugin")
            ):
                plugin_class = attr
                break

        if not plugin_class:
            raise PluginLoadError(name, "No valid plugin class found")

        try:
            instance = plugin_class()
        except Exception as e:
            raise PluginLoadError(name, f"Failed to instantiate: {e}")

        self.register_plugin(name, metadata, instance)
        return instance

    async def validate_plugin(
        self,
        name: str,
        config: dict,
    ) -> list[str]:
        info = self._plugins.get(name)
        if not info:
            raise PluginNotFoundError(name)

        errors = []
        schema = info.metadata.config_schema
        required = schema.get("required", [])
        for key in required:
            if key not in config:
                errors.append(f"Missing required config: {key}")

        instance = info.instance
        if hasattr(instance, "validate"):
            try:
                result = await instance.validate(config)
                if not result:
                    errors.append("Plugin validation failed")
            except Exception as e:
                errors.append(f"Validation error: {e}")

        return errors


_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def register_plugin(
    name: str,
    metadata: PluginMetadata,
    instance: Any,
) -> None:
    get_registry().register_plugin(name, metadata, instance)


def get_plugin(name: str) -> Any:
    return get_registry().get_plugin(name)


def list_plugins(plugin_type: PluginType | None = None) -> list[str]:
    return get_registry().list_plugins(plugin_type)


def plugin_exists(name: str) -> bool:
    return get_registry().plugin_exists(name)
