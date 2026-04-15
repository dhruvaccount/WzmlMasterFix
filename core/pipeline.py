from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.exceptions import (
    PipelineNotFoundError,
    PipelineValidationError,
)


class ErrorPolicy(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"
    RETRY = "retry"


DOWNLOADER_PLUGINS = {
    "aria2": {
        "actions": ["download", "pause", "resume", "cancel"],
        "name": "Aria2 HTTP/FTP/Torrent",
    },
    "qbit": {
        "actions": ["download", "pause", "resume", "cancel"],
        "name": "qBittorrent",
    },
    "jd": {"actions": ["download"], "name": "JDownloader"},
    "mega": {"actions": ["download"], "name": "Mega.nz"},
    "nzb": {"actions": ["download"], "name": "NZB/SABnzbd"},
    "yt_dlp": {"actions": ["download"], "name": "yt-dlp YouTube/Media"},
    "direct": {"actions": ["download"], "name": "Direct URL"},
    "telegram": {"actions": ["download"], "name": "Telegram Files"},
    "gdrive": {"actions": ["download"], "name": "Google Drive"},
    "rclone": {"actions": ["download"], "name": "RClone Multi-Cloud"},
    "link_gen": {"actions": ["generate"], "name": "Direct Link Generator"},
}


UPLOADER_PLUGINS = {
    "gdrive": {"actions": ["upload"], "name": "Google Drive"},
    "rclone": {"actions": ["upload", "transfer"], "name": "RClone Transfer"},
    "telegram": {"actions": ["upload"], "name": "Telegram"},
    "youtube": {"actions": ["upload"], "name": "YouTube Upload"},
    "uphosted": {"actions": ["upload"], "name": "External Hosting"},
}


PROCESSOR_PLUGINS = {
    "extractor": {"actions": ["extract"], "name": "Archive Extraction"},
    "compressor": {"actions": ["zip", "7z", "tar"], "name": "File Compression"},
    "ffmpeg": {
        "actions": ["transcode", "convert", "watermark"],
        "name": "FFmpeg Video",
    },
    "metadata": {"actions": ["extract"], "name": "Metadata Extraction"},
    "thumbnail": {"actions": ["generate", "embed"], "name": "Thumbnail"},
    "splitter": {"actions": ["split"], "name": "File Splitter"},
    "renamer": {"actions": ["rename"], "name": "File Renamer"},
}


ALL_PLUGINS = {}
for p_dict in (DOWNLOADER_PLUGINS, UPLOADER_PLUGINS, PROCESSOR_PLUGINS):
    for p_name, p_info in p_dict.items():
        if p_name in ALL_PLUGINS:
            ALL_PLUGINS[p_name]["actions"].extend(p_info["actions"])
            ALL_PLUGINS[p_name]["actions"] = list(set(ALL_PLUGINS[p_name]["actions"]))
        else:
            ALL_PLUGINS[p_name] = p_info.copy()


@dataclass
class StageConfig:
    path: str = "/tmp/downloads"
    recursive: bool = True
    method: str = "zip"
    format: str = "best"
    quality: str = "best"
    destination: str = "root"
    options: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "StageConfig":
        known = {
            "path",
            "recursive",
            "method",
            "format",
            "quality",
            "destination",
            "options",
        }
        config = cls()
        for key, value in data.items():
            if key in known:
                setattr(config, key, value)
            else:
                config.options[key] = value
        return config

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "recursive": self.recursive,
            "method": self.method,
            "format": self.format,
            "quality": self.quality,
            "destination": self.destination,
            **self.options,
        }


@dataclass
class PipelineStage:
    plugin: str
    action: str
    config: StageConfig = field(default_factory=StageConfig)
    on_error: ErrorPolicy = ErrorPolicy.STOP
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin": self.plugin,
            "action": self.action,
            "config": self.config.to_dict(),
            "on_error": self.on_error,
            "name": self.name,
        }


@dataclass
class PipelineConfig:
    id: str
    name: str
    description: str = ""
    stages: list[PipelineStage] = field(default_factory=list)
    timeout: int = 3600
    enabled: bool = True
    metadata: dict = field(default_factory=dict)

    def validate(self) -> list[str]:
        errors = []

        if not self.stages:
            errors.append("Pipeline must have at least one stage")

        for i, stage in enumerate(self.stages):
            plugin_type, plugin_name = (
                stage.plugin.split(".") if "." in stage.plugin else (None, stage.plugin)
            )

            if plugin_name not in ALL_PLUGINS:
                errors.append(f"Stage {i}: Unknown plugin '{stage.plugin}'")
            else:
                plugin_info = ALL_PLUGINS.get(plugin_name, {})
                if stage.action not in plugin_info.get("actions", []):
                    errors.append(
                        f"Stage {i}: Plugin '{plugin_name}' does not support action '{stage.action}'. "
                        f"Available: {plugin_info.get('actions', [])}"
                    )

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stages": [s.to_dict() for s in self.stages],
            "timeout": self.timeout,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class Pipeline:
    config: PipelineConfig

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def stages(self) -> list[PipelineStage]:
        return self.config.stages

    @property
    def stage_count(self) -> int:
        return len(self.config.stages)

    def to_dict(self) -> dict[str, Any]:
        return self.config.to_dict()

    def validate(self) -> list[str]:
        return self.config.validate()

    def get_stage(self, index: int) -> PipelineStage | None:
        if 0 <= index < len(self.config.stages):
            return self.config.stages[index]
        return None


BUILTIN_PIPELINES: dict[str, Pipeline] = {}
CUSTOM_PIPELINES: dict[str, Pipeline] = {}


def register_pipeline(pipeline: Pipeline, custom: bool = False) -> None:
    errors = pipeline.validate()
    if errors:
        raise PipelineValidationError(pipeline.id, errors)

    if custom:
        CUSTOM_PIPELINES[pipeline.id] = pipeline
    else:
        BUILTIN_PIPELINES[pipeline.id] = pipeline


def unregister_pipeline(pipeline_id: str) -> None:
    if pipeline_id in CUSTOM_PIPELINES:
        del CUSTOM_PIPELINES[pipeline_id]
    elif pipeline_id in BUILTIN_PIPELINES:
        del BUILTIN_PIPELINES[pipeline_id]


def get_pipeline(pipeline_id: str) -> Pipeline:
    pipeline = CUSTOM_PIPELINES.get(pipeline_id) or BUILTIN_PIPELINES.get(pipeline_id)
    if not pipeline:
        raise PipelineNotFoundError(pipeline_id)
    return pipeline


def get_pipelines() -> list[Pipeline]:
    return list(BUILTIN_PIPELINES.values()) + list(CUSTOM_PIPELINES.values())


def list_pipelines() -> list[str]:
    return list(BUILTIN_PIPELINES.keys()) + list(CUSTOM_PIPELINES.keys())


def create_pipeline(
    pipeline_id: str,
    name: str,
    stages: list[dict],
    description: str = "",
    custom: bool = False,
) -> Pipeline:
    stage_objects = []
    for i, stage_def in enumerate(stages):
        if isinstance(stage_def, dict):
            stage = PipelineStage(
                plugin=stage_def.get("plugin", ""),
                action=stage_def.get("action", ""),
                config=StageConfig.from_dict(stage_def.get("config", {})),
                on_error=ErrorPolicy(stage_def.get("on_error", "stop"))
                if isinstance(stage_def.get("on_error"), str)
                else ErrorPolicy.STOP,
                name=stage_def.get("name", f"stage_{i}"),
            )
            stage_objects.append(stage)

    pipeline = Pipeline(
        config=PipelineConfig(
            id=pipeline_id,
            name=name,
            description=description,
            stages=stage_objects,
        )
    )

    register_pipeline(pipeline, custom=custom)
    return pipeline


def get_available_plugins() -> dict[str, dict]:
    return ALL_PLUGINS


def get_plugin_actions(plugin_name: str) -> list[str]:
    return ALL_PLUGINS.get(plugin_name, {}).get("actions", [])


def _create_builtin_pipelines() -> None:
    templates = [
        # Direct
        (
            "gdrive",
            "Direct  GDrive",
            [
                {"plugin": "downloader.direct", "action": "download"},
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "telegram",
            "Direct  Telegram",
            [
                {"plugin": "downloader.direct", "action": "download"},
                {"plugin": "uploader.telegram", "action": "upload"},
            ],
        ),
        # qBit
        (
            "qb_mirror",
            "qBit  GDrive",
            [
                {"plugin": "downloader.qbit", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "qb_leech",
            "qBit  Telegram",
            [
                {"plugin": "downloader.qbit", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.telegram", "action": "upload"},
            ],
        ),
        # JD
        (
            "jd_mirror",
            "JD  GDrive",
            [
                {"plugin": "downloader.jd", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "jd_leech",
            "JD  Telegram",
            [
                {"plugin": "downloader.jd", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.telegram", "action": "upload"},
            ],
        ),
        # NZB
        (
            "nzb_mirror",
            "NZB  GDrive",
            [
                {"plugin": "downloader.nzb", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "nzb_leech",
            "NZB  Telegram",
            [
                {"plugin": "downloader.nzb", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.telegram", "action": "upload"},
            ],
        ),
        # YT-DLP
        (
            "yt_gdrive",
            "YT-DLP  GDrive",
            [
                {"plugin": "downloader.yt_dlp", "action": "download"},
                {
                    "plugin": "processor.ffmpeg",
                    "action": "transcode",
                    "on_error": "continue",
                },
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "yt_telegram",
            "YT-DLP  Telegram",
            [
                {"plugin": "downloader.yt_dlp", "action": "download"},
                {
                    "plugin": "processor.ffmpeg",
                    "action": "transcode",
                    "on_error": "continue",
                },
                {"plugin": "uploader.telegram", "action": "upload"},
            ],
        ),
        # Mega
        (
            "mega_mirror",
            "Mega  GDrive",
            [
                {"plugin": "downloader.mega", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "mega_leech",
            "Mega  Telegram",
            [
                {"plugin": "downloader.mega", "action": "download"},
                {
                    "plugin": "processor.extractor",
                    "action": "extract",
                    "on_error": "continue",
                },
                {
                    "plugin": "processor.renamer",
                    "action": "rename",
                    "on_error": "continue",
                },
                {"plugin": "uploader.telegram", "action": "upload"},
            ],
        ),
        # Clone
        (
            "gdrive_clone",
            "GDrive Clone",
            [
                {"plugin": "downloader.gdrive", "action": "download"},
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        # Legacy mappings (keeping for compatibility if any code uses them)
        (
            "download_upload",
            "Download  Upload",
            [
                {"plugin": "downloader.direct", "action": "download"},
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
        (
            "torrent_gdrive",
            "Torrent  GDrive",
            [
                {"plugin": "downloader.qbit", "action": "download"},
                {"plugin": "uploader.gdrive", "action": "upload"},
            ],
        ),
    ]

    for pipeline_id, name, stages in templates:
        try:
            create_pipeline(pipeline_id, name, stages, custom=False)
        except Exception as e:
            print(f"Error creating pipeline {pipeline_id}: {e}")


_create_builtin_pipelines()
