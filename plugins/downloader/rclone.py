import asyncio
import logging
import os
import json
from typing import Any, Optional

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.rclone_downloader")


class RCloneDownloader(DownloaderPlugin):
    name = "rclone"
    plugin_type = "downloader"

    def __init__(self):
        self._config_path = None
        self._remote = None

    async def initialize(
        self, config_path: str = None, remote: str = "gdrive:"
    ) -> bool:
        self._config_path = config_path or os.path.expanduser(
            "~/.config/rclone/rclone.conf"
        )
        self._remote = remote
        logger.info(f"RClone initialized: {remote}")
        return True

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        dest = config.get("path", "/tmp/downloads")
        remote = config.get("remote", self._remote)

        try:
            import subprocess

            cmd = [
                "rclone",
                "copy",
                f"{remote}:{source}",
                dest,
                "--config",
                self._config_path,
                "--transfers",
                str(config.get("transfers", 4)),
                "--progress",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return PluginResult(
                    success=True,
                    output_path=dest,
                    metadata={"source": source, "dest": dest},
                )
            else:
                return PluginResult(
                    success=False,
                    error=result.stderr,
                )

        except Exception as e:
            logger.error(f"RClone download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def list_remote(self, remote: str = None, path: str = "") -> list:
        try:
            import subprocess

            remote = remote or self._remote
            cmd = [
                "rclone",
                "lsjson",
                f"{remote}:{path}",
                "--config",
                self._config_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return json.loads(result.stdout)
            return []
        except Exception as e:
            logger.error(f"RClone list error: {e}")
            return []

    async def list_remotes(self) -> list:
        try:
            import subprocess

            cmd = ["rclone", "listremotes", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return [r.strip() for r in result.stdout.split("\n") if r]
            return []
        except Exception as e:
            logger.error(f"RClone remotes error: {e}")
            return []

    async def get_config(self) -> dict:
        try:
            import subprocess

            cmd = ["rclone", "config", "show", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return {"output": result.stdout, "error": result.stderr}
        except Exception as e:
            logger.error(f"RClone config error: {e}")
            return {}

    async def size(self, remote: str, path: str = "") -> dict:
        try:
            import subprocess

            cmd = ["rclone", "size", f"{remote}:{path}", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                lines = result.stdout.split("\n")
                data = {}
                for line in lines:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        data[key.strip()] = val.strip()
                return data
            return {}
        except Exception as e:
            logger.error(f"RClone size error: {e}")
            return {}

    async def link(self, remote: str, path: str) -> str:
        try:
            import subprocess

            cmd = ["rclone", "link", f"{remote}:{path}", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"RClone link error: {e}")
            return None

    async def move(self, source: str, dest: str) -> bool:
        try:
            import subprocess

            cmd = ["rclone", "move", source, dest, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone move error: {e}")
            return False

    async def delete(self, remote: str, path: str) -> bool:
        try:
            import subprocess

            cmd = ["rclone", "purge", f"{remote}:{path}", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone delete error: {e}")
            return False

    async def mkdir(self, remote: str, path: str) -> bool:
        try:
            import subprocess

            cmd = ["rclone", "mkdir", f"{remote}:{path}", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone mkdir error: {e}")
            return False

    async def copy(
        self, source: str, dest_remote: str, dest_path: str, transfers: int = 4
    ) -> bool:
        try:
            import subprocess

            cmd = [
                "rclone",
                "copy",
                source,
                f"{dest_remote}:{dest_path}",
                "--config",
                self._config_path,
                "--transfers",
                str(transfers),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone copy error: {e}")
            return False

    async def sync(self, source: str, dest_remote: str, dest_path: str) -> bool:
        try:
            import subprocess

            cmd = [
                "rclone",
                "sync",
                source,
                f"{dest_remote}:{dest_path}",
                "--config",
                self._config_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone sync error: {e}")
            return False

    async def serve(self, remote: str, address: str = ":8080") -> bool:
        try:
            import subprocess

            cmd = ["rclone", "serve", "http", f"{remote}:", "--addr", address]
            self._process = subprocess.Popen(cmd)
            return True
        except Exception as e:
            logger.error(f"RClone serve error: {e}")
            return False

    async def cancel(self) -> bool:
        if hasattr(self, "_process"):
            self._process.terminate()
            return True
        return False
