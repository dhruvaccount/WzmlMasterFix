from plugins.base import (
    PluginBase,
    DownloaderPlugin,
    UploaderPlugin,
    ProcessorPlugin,
    PluginContext,
    PluginResult,
    PluginType,
)

from plugins.base import get_available_plugins as _get_available_plugins


def get_available_plugins() -> dict:
    return _get_available_plugins()


__all__ = [
    "PluginBase",
    "DownloaderPlugin",
    "UploaderPlugin",
    "ProcessorPlugin",
    "PluginContext",
    "PluginResult",
    "PluginType",
    "get_available_plugins",
]
