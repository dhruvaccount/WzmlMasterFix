import logging
from typing import Optional

logger = logging.getLogger("wzml.plugin_loader")

_plugin_instances: dict = {}


def get_plugin(name: str) -> Optional[object]:
    return _plugin_instances.get(name)


async def load_plugins() -> None:
    downloaders = [
        ("aria2", "plugins.downloader.aria2", "Aria2Downloader"),
        ("qbit", "plugins.downloader.qbit", "QBitDownloader"),
        ("jd", "plugins.downloader.jd", "JDownloader"),
        ("mega", "plugins.downloader.mega", "MegaDownloader"),
        ("nzb", "plugins.downloader.nzb", "NZBDownloader"),
        ("yt_dlp", "plugins.downloader.yt_dlp", "YTDlpDownloader"),
        ("direct", "plugins.downloader.direct", "DirectDownloader"),
        ("telegram", "plugins.downloader.telegram", "TelegramDownloader"),
        ("gdrive", "plugins.downloader.gdrive", "GDriveDownloader"),
        ("rclone", "plugins.downloader.rclone", "RCloneDownloader"),
    ]

    uploaders = [
        ("gdrive", "plugins.uploader.gdrive", "GDriveUploader"),
        ("rclone", "plugins.uploader.rclone", "RCloneUploader"),
        ("telegram", "plugins.uploader.telegram", "TelegramUploader"),
        ("youtube", "plugins.uploader.youtube", "YouTubeUploader"),
        ("uphosted", "plugins.uploader.uphosted", "UphosterUploader"),
    ]

    processors = [
        ("extractor", "plugins.processor.extractor", "ExtractorProcessor"),
        ("compressor", "plugins.processor.compressor", "CompressorProcessor"),
        ("ffmpeg", "plugins.processor.ffmpeg", "FFmpegProcessor"),
        ("metadata", "plugins.processor.metadata", "MetadataProcessor"),
        ("thumbnail", "plugins.processor.thumbnail", "ThumbnailProcessor"),
        ("splitter", "plugins.processor.splitter", "SplitterProcessor"),
        ("renamer", "plugins.processor.renamer", "RenamerProcessor"),
    ]

    all_plugins = downloaders + uploaders + processors

    for name, module_path, class_name in all_plugins:
        try:
            from importlib import import_module

            module = import_module(module_path)
            plugin_class = getattr(module, class_name)
            instance = plugin_class()
            _plugin_instances[name] = instance
            logger.info(f"Loaded plugin: {name}")
        except Exception as e:
            logger.warning(f"Failed to load plugin {name}: {e}")

    logger.info(f"Loaded {len(_plugin_instances)} plugins")


def unload_plugins() -> None:
    global _plugin_instances
    _plugin_instances.clear()
