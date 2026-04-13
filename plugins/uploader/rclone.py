import asyncio
import logging
import os
import subprocess
from typing import Any, Optional

from plugins.base import UploaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.rclone_uploader")


class RCloneUploader(UploaderPlugin):
    name = "rclone"
    plugin_type = "uploader"

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
        logger.info(f"RClone uploader initialized: {remote}")
        return True

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        file_path = context.source
        remote = config.get("remote", self._remote)
        dest_path = config.get("dest_path", "")

        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            if os.path.isdir(file_path):
                cmd = [
                    "rclone",
                    "copy",
                    file_path,
                    remote,
                    "--config",
                    self._config_path,
                ]
            else:
                dest = f"{remote}:{dest_path}" if dest_path else remote
                cmd = [
                    "rclone",
                    "copyto",
                    file_path,
                    dest,
                    "--config",
                    self._config_path,
                ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return PluginResult(
                    success=True,
                    output_path=file_path,
                    metadata={"source": file_path, "dest": remote},
                )
            else:
                return PluginResult(success=False, error=result.stderr)

        except Exception as e:
            logger.error(f"RClone upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def copy(self, source: str, dest: str) -> bool:
        try:
            cmd = ["rclone", "copyto", source, dest, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone copy error: {e}")
            return False

    async def move(self, source: str, dest: str) -> bool:
        try:
            cmd = ["rclone", "moveto", source, dest, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone move error: {e}")
            return False

    async def delete(self, remote_path: str) -> bool:
        try:
            cmd = ["rclone", "purge", remote_path, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone delete error: {e}")
            return False

    async def list_remotes(self) -> list:
        try:
            cmd = ["rclone", "listremotes", "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return [r.strip() for r in result.stdout.split("\n") if r]
            return []
        except Exception as e:
            logger.error(f"RClone list remotes error: {e}")
            return []

    async def list_files(self, remote_path: str) -> list:
        try:
            cmd = ["rclone", "lsjson", remote_path, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                import json

                return json.loads(result.stdout)
            return []
        except Exception as e:
            logger.error(f"RClone list files error: {e}")
            return []

    async def size(self, remote_path: str) -> dict:
        try:
            cmd = ["rclone", "size", remote_path, "--config", self._config_path]
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

    async def link(self, remote_path: str) -> str:
        try:
            cmd = ["rclone", "link", remote_path, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"RClone link error: {e}")
            return None

    async def mkdir(self, remote_path: str) -> bool:
        try:
            cmd = ["rclone", "mkdir", remote_path, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone mkdir error: {e}")
            return False

    async def sync(self, source: str, dest: str) -> bool:
        try:
            cmd = ["rclone", "sync", source, dest, "--config", self._config_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"RClone sync error: {e}")
            return False
