import os
import logging
import yaml
from typing import Any, Optional, Dict
from pathlib import Path

from config._base import BaseConfig
from config.telegram import (
    TelegramConfig,
    DatabaseConfig,
    LimitsConfig,
    BotSettingsConfig,
    TaskToolsConfig,
    GDriveConfig,
    RcloneConfig,
    MegaConfig,
    JDownloaderConfig,
    LeechConfig,
    LogsConfig,
    RSSConfig,
    SearchConfig,
    DisableConfig,
    TelegraphConfig,
    YTConfig,
    UpdateConfig,
)

logger = logging.getLogger("wzml.config")

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.py")
CONFIG_YAML = os.getenv("CONFIG_YAML", "config.yml")

ALL_CONFIGS: Dict[str, Any] = {}
_config: Optional["Config"] = None


def get_config(group: str = None) -> Optional[Any]:
    if group is None:
        return get_config_obj()
    return ALL_CONFIGS.get(group)


def load_configs():
    global ALL_CONFIGS

    config_data = _load_config_data()

    telegram_cfg = TelegramConfig()
    if "telegram" in config_data:
        telegram_cfg._load_from_attrs(config_data["telegram"])
    else:
        telegram_cfg.load()
    ALL_CONFIGS["telegram"] = telegram_cfg

    database_cfg = DatabaseConfig()
    if "database" in config_data:
        database_cfg._load_from_attrs(config_data["database"])
    else:
        database_cfg.load()
    ALL_CONFIGS["database"] = database_cfg

    limits_cfg = LimitsConfig()
    if "limits" in config_data:
        limits_cfg._load_from_attrs(config_data["limits"])
    else:
        limits_cfg.load()
    ALL_CONFIGS["limits"] = limits_cfg

    task_tools_cfg = TaskToolsConfig()
    if "task_tools" in config_data:
        task_tools_cfg._load_from_attrs(config_data["task_tools"])
    else:
        task_tools_cfg.load()
    ALL_CONFIGS["task_tools"] = task_tools_cfg

    gdrive_cfg = GDriveConfig()
    if "gdrive" in config_data:
        gdrive_cfg._load_from_attrs(config_data["gdrive"])
    else:
        gdrive_cfg.load()
    ALL_CONFIGS["gdrive"] = gdrive_cfg

    rclone_cfg = RcloneConfig()
    if "rclone" in config_data:
        rclone_cfg._load_from_attrs(config_data["rclone"])
    else:
        rclone_cfg.load()
    ALL_CONFIGS["rclone"] = rclone_cfg

    mega_cfg = MegaConfig()
    if "mega" in config_data:
        mega_cfg._load_from_attrs(config_data["mega"])
    else:
        mega_cfg.load()
    ALL_CONFIGS["mega"] = mega_cfg

    jd_cfg = JDownloaderConfig()
    if "jdownloader" in config_data:
        jd_cfg._load_from_attrs(config_data["jdownloader"])
    else:
        jd_cfg.load()
    ALL_CONFIGS["jdownloader"] = jd_cfg

    leech_cfg = LeechConfig()
    if "leech" in config_data:
        leech_cfg._load_from_attrs(config_data["leech"])
    else:
        leech_cfg.load()
    ALL_CONFIGS["leech"] = leech_cfg

    logs_cfg = LogsConfig()
    if "logs" in config_data:
        logs_cfg._load_from_attrs(config_data["logs"])
    else:
        logs_cfg.load()
    ALL_CONFIGS["logs"] = logs_cfg

    rss_cfg = RSSConfig()
    if "rss" in config_data:
        rss_cfg._load_from_attrs(config_data["rss"])
    else:
        rss_cfg.load()
    ALL_CONFIGS["rss"] = rss_cfg

    search_cfg = SearchConfig()
    if "search" in config_data:
        search_cfg._load_from_attrs(config_data["search"])
    else:
        search_cfg.load()
    ALL_CONFIGS["search"] = search_cfg

    bot_settings_cfg = BotSettingsConfig()
    if "bot_settings" in config_data:
        bot_settings_cfg._load_from_attrs(config_data["bot_settings"])
    else:
        bot_settings_cfg.load()
    ALL_CONFIGS["bot_settings"] = bot_settings_cfg

    disable_cfg = DisableConfig()
    if "disable" in config_data:
        disable_cfg._load_from_attrs(config_data["disable"])
    else:
        disable_cfg.load()
    ALL_CONFIGS["disable"] = disable_cfg

    telegraph_cfg = TelegraphConfig()
    if "telegraph" in config_data:
        telegraph_cfg._load_from_attrs(config_data["telegraph"])
    else:
        telegraph_cfg.load()
    ALL_CONFIGS["telegraph"] = telegraph_cfg

    yt_cfg = YTConfig()
    if "yt" in config_data:
        yt_cfg._load_from_attrs(config_data["yt"])
    else:
        yt_cfg.load()
    ALL_CONFIGS["yt"] = yt_cfg

    update_cfg = UpdateConfig()
    if "update" in config_data:
        update_cfg._load_from_attrs(config_data["update"])
    else:
        update_cfg.load()
    ALL_CONFIGS["update"] = update_cfg

    for name in ALL_CONFIGS:
        logger.info(f"Loaded config group: {name}")

    return ALL_CONFIGS


def _load_config_data() -> Dict[str, Any]:
    data = {}

    if os.path.exists(CONFIG_YAML):
        try:
            with open(CONFIG_YAML, "r") as f:
                data = yaml.safe_load(f) or {}
            logger.info(f"Loaded config from {CONFIG_YAML}")
            return data
        except Exception as e:
            logger.warning(f"Failed to load {CONFIG_YAML}: {e}")

    try:
        import config as user_config

        for key in dir(user_config):
            if key.startswith("_"):
                continue
            value = getattr(user_config, key, None)
            if value is not None and key.isupper():
                pass
    except ImportError:
        pass

    return data


def reload_configs():
    global ALL_CONFIGS
    for name, cfg in ALL_CONFIGS.items():
        try:
            cfg.reload()
            logger.info(f"Reloaded config group: {name}")
        except Exception as e:
            logger.error(f"Failed to reload config {name}: {e}")


def get_setting(group: str, key: str, default: Any = None) -> Any:
    cfg = ALL_CONFIGS.get(group)
    if cfg:
        return cfg.get(key, default)
    return default


def set_setting(group: str, key: str, value: Any):
    cfg = ALL_CONFIGS.get(group)
    if cfg:
        cfg.set(key, value)


class Config:
    telegram: "TelegramConfig"
    database: "DatabaseConfig"
    limits: "LimitsConfig"
    task_tools: "TaskToolsConfig"
    gdrive: "GDriveConfig"
    rclone: "RcloneConfig"
    mega: "MegaConfig"
    jdownloader: "JDownloaderConfig"
    leech: "LeechConfig"
    logs: "LogsConfig"
    rss: "RSSConfig"
    search: "SearchConfig"
    bot_settings: "BotSettingsConfig"
    disable: "DisableConfig"
    telegraph: "TelegraphConfig"
    yt: "YTConfig"
    update: "UpdateConfig"

    def __init__(self):
        self.telegram = TelegramConfig()
        self.database = DatabaseConfig()
        self.limits = LimitsConfig()
        self.task_tools = TaskToolsConfig()
        self.gdrive = GDriveConfig()
        self.rclone = RcloneConfig()
        self.mega = MegaConfig()
        self.jdownloader = JDownloaderConfig()
        self.leech = LeechConfig()
        self.logs = LogsConfig()
        self.rss = RSSConfig()
        self.search = SearchConfig()
        self.bot_settings = BotSettingsConfig()
        self.disable = DisableConfig()
        self.telegraph = TelegraphConfig()
        self.yt = YTConfig()
        self.update = UpdateConfig()

    def load_all(self):
        load_configs()
        self.telegram = ALL_CONFIGS.get("telegram", TelegramConfig())
        self.database = ALL_CONFIGS.get("database", DatabaseConfig())
        self.limits = ALL_CONFIGS.get("limits", LimitsConfig())
        self.task_tools = ALL_CONFIGS.get("task_tools", TaskToolsConfig())
        self.gdrive = ALL_CONFIGS.get("gdrive", GDriveConfig())
        self.rclone = ALL_CONFIGS.get("rclone", RcloneConfig())
        self.mega = ALL_CONFIGS.get("mega", MegaConfig())
        self.jdownloader = ALL_CONFIGS.get("jdownloader", JDownloaderConfig())
        self.leech = ALL_CONFIGS.get("leech", LeechConfig())
        self.logs = ALL_CONFIGS.get("logs", LogsConfig())
        self.rss = ALL_CONFIGS.get("rss", RSSConfig())
        self.search = ALL_CONFIGS.get("search", SearchConfig())
        self.bot_settings = ALL_CONFIGS.get("bot_settings", BotSettingsConfig())
        self.disable = ALL_CONFIGS.get("disable", DisableConfig())
        self.telegraph = ALL_CONFIGS.get("telegraph", TelegraphConfig())
        self.yt = ALL_CONFIGS.get("yt", YTConfig())
        self.update = ALL_CONFIGS.get("update", UpdateConfig())

    def reload_all(self):
        reload_configs()


def get_config_obj() -> Config:
    global _config
    if _config is None:
        _config = Config()
        _config.load_all()
    return _config


config = get_config_obj()

__all__ = [
    "Config",
    "BaseConfig",
    "get_config",
    "load_configs",
    "reload_configs",
    "get_setting",
    "set_setting",
    "config",
    "TelegramConfig",
    "DatabaseConfig",
    "LimitsConfig",
    "GDriveConfig",
    "RcloneConfig",
    "MegaConfig",
    "JDownloaderConfig",
    "LeechConfig",
    "LogsConfig",
    "RSSConfig",
    "SearchConfig",
    "BotSettingsConfig",
    "DisableConfig",
    "TelegraphConfig",
    "YTConfig",
    "UpdateConfig",
]
