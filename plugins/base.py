from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class PluginType(StrEnum):
    DOWNLOADER = "downloader"
    UPLOADER = "uploader"
    PROCESSOR = "processor"


@dataclass
class PluginContext:
    task_id: str
    source: str
    destination: str
    config: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    progress: float = 0.0
    speed: float = 0.0
    eta: int = 0


@dataclass
class PluginResult:
    success: bool
    output_path: str | None = None
    output_paths: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    progress: float = 100.0
    speed: float = 0.0


class PluginBase(ABC):
    name: str = ""
    plugin_type: PluginType = PluginType.DOWNLOADER

    async def execute(self, context: PluginContext, config: dict) -> PluginResult:
        return PluginResult(success=False, error="Not implemented")

    async def validate(self, config: dict) -> bool:
        return True

    async def get_status(self) -> dict:
        return {
            "name": self.name,
            "type": self.plugin_type,
            "status": "idle",
        }


class DownloaderPlugin(PluginBase):
    plugin_type: PluginType = PluginType.DOWNLOADER

    @abstractmethod
    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        pass

    async def pause(self) -> bool:
        return False

    async def resume(self) -> bool:
        return False

    async def cancel(self) -> bool:
        return False


class UploaderPlugin(PluginBase):
    plugin_type: PluginType = PluginType.UPLOADER

    @abstractmethod
    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        pass


class ProcessorPlugin(PluginBase):
    plugin_type: PluginType = PluginType.PROCESSOR

    @abstractmethod
    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        pass


def get_available_plugins() -> dict[str, dict]:
    from core.pipeline import ALL_PLUGINS

    return ALL_PLUGINS
