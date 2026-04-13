from config._base import BaseConfig


class TelegramConfig(BaseConfig):
    _prefix = "TELEGRAM_"
    _group_name = "telegram"

    BOT_TOKEN: str = ""
    API: int = 0
    HASH: str = ""
    OWNER_ID: int = 0
    USER_SESSION_STRING: str = ""
    HELPER_TOKENS: str = ""
    PROXY: dict = {}
    BASE_URL: str = ""
    BOT_USERNAME: str = ""
    HYDRA_IP: str = ""
    HYDRA_API_KEY: str = ""
    CMD_SUFFIX: str = ""
    DEFAULT_LANG: str = "en"
    TIMEZONE: str = "Asia/Kolkata"
    AUTHORIZED_CHATS: list = []
    SUDO_USERS: list = []

    def load(self):
        self.BOT_TOKEN = self._get_env("BOT_TOKEN", self.BOT_TOKEN)
        self.API = self._get_env("API", 0, int)
        self.HASH = self._get_env("HASH", self.HASH)
        self.OWNER_ID = self._get_env("OWNER_ID", 0, int)
        self.USER_SESSION_STRING = self._get_env(
            "USER_SESSION_STRING", self.USER_SESSION_STRING
        )
        self.HELPER_TOKENS = self._get_env("HELPER_TOKENS", self.HELPER_TOKENS)
        self.BASE_URL = self._get_env("BASE_URL", self.BASE_URL)
        self.BOT_USERNAME = self._get_env("BOT_USERNAME", self.BOT_USERNAME)
        self.HYDRA_IP = self._get_env("HYDRA_IP", self.HYDRA_IP)
        self.HYDRA_API_KEY = self._get_env("HYDRA_API_KEY", self.HYDRA_API_KEY)
        self.CMD_SUFFIX = self._get_env("CMD_SUFFIX", self.CMD_SUFFIX)
        self.DEFAULT_LANG = self._get_env("DEFAULT_LANG", self.DEFAULT_LANG)
        self.TIMEZONE = self._get_env("TIMEZONE", self.TIMEZONE)
        self.AUTHORIZED_CHATS = self._get_env("AUTHORIZED_CHATS", [], list)
        self.SUDO_USERS = self._get_env("SUDO_USERS", [], list)

    def validate(self) -> bool:
        return bool(self.BOT_TOKEN and self.API and self.HASH and self.OWNER_ID)


class DatabaseConfig(BaseConfig):
    _prefix = "DB_"
    _group_name = "database"

    DATABASE_URL: str = ""
    MONGO_DB_NAME: str = "wzmlx"
    DATABASE_CLIENT: str = "mongodb"

    def load(self):
        self.DATABASE_URL = self._get_env("DATABASE_URL", self.DATABASE_URL)
        self.MONGO_DB_NAME = self._get_env("MONGO_DB_NAME", self.MONGO_DB_NAME)
        self.DATABASE_CLIENT = self._get_env("DATABASE_CLIENT", self.DATABASE_CLIENT)


class LimitsConfig(BaseConfig):
    _prefix = "LIMIT_"
    _group_name = "limits"

    DIRECT_LIMIT: int = 0
    MEGA_LIMIT: int = 0
    TORRENT_LIMIT: int = 0
    GD_DL_LIMIT: int = 0
    RC_DL_LIMIT: int = 0
    CLONE_LIMIT: int = 0
    JD_LIMIT: int = 0
    NZB_LIMIT: int = 0
    YTDLP_LIMIT: int = 0
    PLAYLIST_LIMIT: int = 0
    LEECH_LIMIT: int = 0
    EXTRACT_LIMIT: int = 0
    ARCHIVE_LIMIT: int = 0
    STORAGE_LIMIT: int = 0
    BOT_MAX_TASKS: int = 0
    USER_MAX_TASKS: int = 0
    USER_TIME_INTERVAL: int = 0
    VERIFY_TIMEOUT: int = 0
    STATUS_LIMIT: int = 10
    STATUS_UPDATE_INTERVAL: int = 15
    QUEUE_ALL: int = 0
    QUEUE_DOWNLOAD: int = 0
    QUEUE_UPLOAD: int = 0
    TORRENT_TIMEOUT: int = 0
    BASE_URL_PORT: int = 0
    WEB_PINCODE: bool = True
    DEFAULT_UPLOAD: str = "rc"
    MAX_WORKERS: int = 4
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080

    def load(self):
        self.MAX_WORKERS = self._get_env("MAX_WORKERS", 4, int)
        self.API_HOST = self._get_env("API_HOST", self.API_HOST)
        self.API_PORT = self._get_env("API_PORT", 8080, int)
        self.DIRECT_LIMIT = self._get_env("DIRECT", 0, int)
        self.MEGA_LIMIT = self._get_env("MEGA", 0, int)
        self.TORRENT_LIMIT = self._get_env("TORRENT", 0, int)
        self.GD_DL_LIMIT = self._get_env("GD_DL", 0, int)
        self.RC_DL_LIMIT = self._get_env("RC_DL", 0, int)
        self.CLONE_LIMIT = self._get_env("CLONE", 0, int)
        self.JD_LIMIT = self._get_env("JD", 0, int)
        self.NZB_LIMIT = self._get_env("NZB", 0, int)
        self.YTDLP_LIMIT = self._get_env("YTDLP", 0, int)
        self.PLAYLIST_LIMIT = self._get_env("PLAYLIST", 0, int)
        self.LEECH_LIMIT = self._get_env("LEECH", 0, int)
        self.EXTRACT_LIMIT = self._get_env("EXTRACT", 0, int)
        self.ARCHIVE_LIMIT = self._get_env("ARCHIVE", 0, int)
        self.STORAGE_LIMIT = self._get_env("STORAGE", 0, int)
        self.BOT_MAX_TASKS = self._get_env("BOT_MAX_TASKS", 0, int)
        self.USER_MAX_TASKS = self._get_env("USER_MAX_TASKS", 0, int)
        self.USER_TIME_INTERVAL = self._get_env("USER_TIME_INTERVAL", 0, int)
        self.VERIFY_TIMEOUT = self._get_env("VERIFY_TIMEOUT", 0, int)
        self.STATUS_LIMIT = self._get_env("STATUS_LIMIT", 10, int)
        self.STATUS_UPDATE_INTERVAL = self._get_env("STATUS_UPDATE_INTERVAL", 15, int)
        self.QUEUE_ALL = self._get_env("QUEUE_ALL", 0, int)
        self.QUEUE_DOWNLOAD = self._get_env("QUEUE_DOWNLOAD", 0, int)
        self.QUEUE_UPLOAD = self._get_env("QUEUE_UPLOAD", 0, int)
        self.TORRENT_TIMEOUT = self._get_env("TORRENT_TIMEOUT", 0, int)
        self.BASE_URL_PORT = self._get_env("BASE_URL_PORT", 0, int)
        self.WEB_PINCODE = self._get_env("WEB_PINCODE", True, bool)
        self.DEFAULT_UPLOAD = self._get_env("DEFAULT_UPLOAD", self.DEFAULT_UPLOAD)


class BotSettingsConfig(BaseConfig):
    _prefix = "BOT_"
    _group_name = "bot_settings"

    BOT_PM: bool = False
    SET_COMMANDS: bool = True
    INCOMPLETE_TASK_NOTIFIER: bool = False
    MEDIA_STORE: bool = True
    NAME_SWAP: str = ""

    def load(self):
        self.BOT_PM = self._get_env("BOT_PM", False, bool)
        self.SET_COMMANDS = self._get_env("SET_COMMANDS", True, bool)
        self.INCOMPLETE_TASK_NOTIFIER = self._get_env(
            "INCOMPLETE_TASK_NOTIFIER", False, bool
        )
        self.MEDIA_STORE = self._get_env("MEDIA_STORE", True, bool)
        self.NAME_SWAP = self._get_env("NAME_SWAP", self.NAME_SWAP)


class TaskToolsConfig(BaseConfig):
    _prefix = "TASK_"
    _group_name = "task_tools"

    FORCE_SUB_IDS: list = []

    def load(self):
        self.FORCE_SUB_IDS = self._get_env("FORCE_SUB_IDS", [], list)


class GDriveConfig(BaseConfig):
    _prefix = "GDRIVE_"
    _group_name = "gdrive"

    GDRIVE_ID: str = ""
    GD_DESP: str = "Uploaded with WZ Bot"
    IS_TEAM_DRIVE: bool = False
    STOP_DUPLICATE: bool = False
    INDEX_URL: str = ""
    USE_SERVICE_ACCOUNTS: bool = False

    def load(self):
        self.GDRIVE_ID = self._get_env("GDRIVE_ID", self.GDRIVE_ID)
        self.GD_DESP = self._get_env("GD_DESP", self.GD_DESP)
        self.IS_TEAM_DRIVE = self._get_env("IS_TEAM_DRIVE", False, bool)
        self.STOP_DUPLICATE = self._get_env("STOP_DUPLICATE", False, bool)
        self.INDEX_URL = self._get_env("INDEX_URL", self.INDEX_URL)
        self.USE_SERVICE_ACCOUNTS = self._get_env("USE_SERVICE_ACCOUNTS", False, bool)


class RcloneConfig(BaseConfig):
    _prefix = "RCLONE_"
    _group_name = "rclone"

    RCLONE_PATH: str = ""
    RCLONE_FLAGS: dict = {}
    RCLONE_SERVE_URL: str = ""
    SHOW_CLOUD_LINK: bool = True
    RCLONE_SERVE_PORT: int = 0
    RCLONE_SERVE_USER: str = ""
    RCLONE_SERVE_PASS: str = ""

    def load(self):
        self.RCLONE_PATH = self._get_env("RCLONE_PATH", self.RCLONE_PATH)
        self.RCLONE_FLAGS = self._get_env("FLAGS", {}, dict)
        self.RCLONE_SERVE_URL = self._get_env("SERVE_URL", self.RCLONE_SERVE_URL)
        self.SHOW_CLOUD_LINK = self._get_env("SHOW_CLOUD_LINK", True, bool)
        self.RCLONE_SERVE_PORT = self._get_env("SERVE_PORT", 0, int)
        self.RCLONE_SERVE_USER = self._get_env("SERVE_USER", self.RCLONE_SERVE_USER)
        self.RCLONE_SERVE_PASS = self._get_env("SERVE_PASS", self.RCLONE_SERVE_PASS)


class MegaConfig(BaseConfig):
    _prefix = "MEGA_"
    _group_name = "mega"

    MEGA_EMAIL: str = ""
    MEGA_PASSWORD: str = ""

    def load(self):
        self.MEGA_EMAIL = self._get_env("MEGA_EMAIL", self.MEGA_EMAIL)
        self.MEGA_PASSWORD = self._get_env("MEGA_PASSWORD", self.MEGA_PASSWORD)


class JDownloaderConfig(BaseConfig):
    _prefix = "JD_"
    _group_name = "jdownloader"

    JD_EMAIL: str = ""
    JD_PASS: str = ""

    def load(self):
        self.JD_EMAIL = self._get_env("JD_EMAIL", self.JD_EMAIL)
        self.JD_PASS = self._get_env("JD_PASS", self.JD_PASS)


class SabnzbdConfig(BaseConfig):
    _prefix = "SABNZBD_"
    _group_name = "sabnzbd"

    USENET_SERVERS: list = []

    def load(self):
        self.USENET_SERVERS = []


class LeechConfig(BaseConfig):
    _prefix = "LEECH_"
    _group_name = "leech"

    LEECH_SPLIT_SIZE: int = 0
    AS_DOCUMENT: bool = False
    EQUAL_SPLITS: bool = False
    MEDIA_GROUP: bool = False
    USER_TRANSMISSION: bool = True
    HYBRID_LEECH: bool = True
    LEECH_PREFIX: str = ""
    LEECH_SUFFIX: str = ""
    LEECH_FONT: str = ""
    LEECH_CAPTION: str = ""
    THUMBNAIL_LAYOUT: str = ""
    DELETE_LINKS: bool = False
    FFMPEG_CMDS: dict = {}
    UPLOAD_PATHS: dict = {}

    def load(self):
        self.LEECH_SPLIT_SIZE = self._get_env("LEECH_SPLIT_SIZE", 0, int)
        self.AS_DOCUMENT = self._get_env("AS_DOCUMENT", False, bool)
        self.EQUAL_SPLITS = self._get_env("EQUAL_SPLITS", False, bool)
        self.MEDIA_GROUP = self._get_env("MEDIA_GROUP", False, bool)
        self.USER_TRANSMISSION = self._get_env("USER_TRANSMISSION", True, bool)
        self.HYBRID_LEECH = self._get_env("HYBRID_LEECH", True, bool)
        self.LEECH_PREFIX = self._get_env("LEECH_PREFIX", self.LEECH_PREFIX)
        self.LEECH_SUFFIX = self._get_env("LEECH_SUFFIX", self.LEECH_SUFFIX)
        self.LEECH_FONT = self._get_env("LEECH_FONT", self.LEECH_FONT)
        self.LEECH_CAPTION = self._get_env("LEECH_CAPTION", self.LEECH_CAPTION)
        self.THUMBNAIL_LAYOUT = self._get_env("THUMBNAIL_LAYOUT", self.THUMBNAIL_LAYOUT)
        self.DELETE_LINKS = self._get_env("DELETE_LINKS", False, bool)
        self.FFMPEG_CMDS = self._get_env("FFMPEG_CMDS", {}, dict)
        self.UPLOAD_PATHS = self._get_env("UPLOAD_PATHS", {}, dict)


class LogsConfig(BaseConfig):
    _prefix = "LOG_"
    _group_name = "logs"

    LEECH_DUMP_CHAT: int = 0
    LINKS_LOG_ID: int = 0
    MIRROR_LOG_ID: int = 0
    CLEAN_LOG_MSG: bool = False
    LOGIN_PASS: str = ""

    def load(self):
        self.LEECH_DUMP_CHAT = self._get_env("LEECH_DUMP_CHAT", 0, int)
        self.LINKS_LOG_ID = self._get_env("LINKS_LOG_ID", 0, int)
        self.MIRROR_LOG_ID = self._get_env("MIRROR_LOG_ID", 0, int)
        self.CLEAN_LOG_MSG = self._get_env("CLEAN_LOG_MSG", False, bool)
        self.LOGIN_PASS = self._get_env("LOGIN_PASS", self.LOGIN_PASS)


class RSSConfig(BaseConfig):
    _prefix = "RSS_"
    _group_name = "rss"

    RSS_DELAY: int = 600
    RSS_CHAT: int = 0
    RSS_SIZE_LIMIT: int = 0

    def load(self):
        self.RSS_DELAY = self._get_env("RSS_DELAY", 600, int)
        self.RSS_CHAT = self._get_env("RSS_CHAT", 0, int)
        self.RSS_SIZE_LIMIT = self._get_env("RSS_SIZE_LIMIT", 0, int)


class SearchConfig(BaseConfig):
    _prefix = "SEARCH_"
    _group_name = "search"

    SEARCH_API_LINK: str = ""
    SEARCH_LIMIT: int = 0
    SEARCH_PLUGINS: list = []
    FILELION_API: str = ""
    STREAMWISH_API: str = ""
    INSTADL_API: str = ""
    EXCLUDED_EXTENSIONS: list = []
    IMDB_TEMPLATE: str = ""

    def load(self):
        self.SEARCH_API_LINK = self._get_env("SEARCH_API_LINK", self.SEARCH_API_LINK)
        self.SEARCH_LIMIT = self._get_env("SEARCH_LIMIT", 0, int)
        self.SEARCH_PLUGINS = self._get_env("SEARCH_PLUGINS", [], list)
        self.FILELION_API = self._get_env("FILELION_API", self.FILELION_API)
        self.STREAMWISH_API = self._get_env("STREAMWISH_API", self.STREAMWISH_API)
        self.INSTADL_API = self._get_env("INSTADL_API", self.INSTADL_API)
        self.EXCLUDED_EXTENSIONS = self._get_env("EXCLUDED_EXTENSIONS", [], list)
        self.IMDB_TEMPLATE = self._get_env("IMDB_TEMPLATE", self.IMDB_TEMPLATE)


class DisableConfig(BaseConfig):
    _prefix = "DISABLE_"
    _group_name = "disable"

    TORRENTS: bool = False
    LEECH: bool = False
    BULK: bool = False
    MULTI: bool = False
    SEED: bool = False
    FF_MODE: bool = False

    def load(self):
        self.TORRENTS = self._get_env("TORRENTS", False, bool)
        self.LEECH = self._get_env("LEECH", False, bool)
        self.BULK = self._get_env("BULK", False, bool)
        self.MULTI = self._get_env("MULTI", False, bool)
        self.SEED = self._get_env("SEED", False, bool)
        self.FF_MODE = self._get_env("FF_MODE", False, bool)


class TelegraphConfig(BaseConfig):
    _prefix = "TELEGRAPH_"
    _group_name = "telegraph"

    AUTHOR_NAME: str = "WZML-X"
    AUTHOR_URL: str = "https://t.me/WZML_X"

    def load(self):
        self.AUTHOR_NAME = self._get_env("AUTHOR_NAME", self.AUTHOR_NAME)
        self.AUTHOR_URL = self._get_env("AUTHOR_URL", self.AUTHOR_URL)


class YTConfig(BaseConfig):
    _prefix = "YT_"
    _group_name = "yt"

    YT_DESP: str = "Uploaded to YouTube by WZML-X bot"
    YT_TAGS: list = ["telegram", "bot", "youtube"]
    YT_CATEGORY_ID: int = 22
    YT_PRIVACY_STATUS: str = "unlisted"
    YT_DLP_OPTIONS: dict = {}

    def load(self):
        self.YT_DESP = self._get_env("YT_DESP", self.YT_DESP)
        self.YT_TAGS = self._get_env("YT_TAGS", ["telegram", "bot", "youtube"], list)
        self.YT_CATEGORY_ID = self._get_env("YT_CATEGORY_ID", 22, int)
        self.YT_PRIVACY_STATUS = self._get_env(
            "YT_PRIVACY_STATUS", self.YT_PRIVACY_STATUS
        )


class UpdateConfig(BaseConfig):
    _prefix = "UPDATE_"
    _group_name = "update"

    UPSTREAM_REPO: str = ""
    UPSTREAM_BRANCH: str = "master"
    UPDATE_PKGS: bool = True

    def load(self):
        self.UPSTREAM_REPO = self._get_env("UPSTREAM_REPO", self.UPSTREAM_REPO)
        self.UPSTREAM_BRANCH = self._get_env("UPSTREAM_BRANCH", "master")
        self.UPDATE_PKGS = self._get_env("UPDATE_PKGS", True, bool)


__all__ = [
    "TelegramConfig",
    "DatabaseConfig",
    "LimitsConfig",
    "BotSettingsConfig",
    "TaskToolsConfig",
    "GDriveConfig",
    "RcloneConfig",
    "MegaConfig",
    "JDownloaderConfig",
    "SabnzbdConfig",
    "LeechConfig",
    "LogsConfig",
    "RSSConfig",
    "SearchConfig",
    "DisableConfig",
    "TelegraphConfig",
    "YTConfig",
    "UpdateConfig",
]
