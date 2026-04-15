import asyncio
import logging
import os
import re
import time
from typing import Any, Optional

from plugins.base import UploaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.rclone_uploader")


class RCloneUploader(UploaderPlugin):
    name = "rclone"
    plugin_type = "uploader"

    def __init__(self):
        self._config_path = None
        self._remote = None
        self._active_processes = {}
        # Regex for rclone --stats=1s output:
        # Transferred:   	    5.630 MiB / 14.542 MiB, 39%, 5.617 MiB/s, ETA 1s
        self._stats_regex = re.compile(
            r"Transferred:\s+([\d\.]+)\s+([a-zA-Z]+)\s+/\s+([\d\.]+)\s+([a-zA-Z]+),\s+(\d+)%,\s+([\d\.]+)\s+([a-zA-Z]+/s),\s+ETA\s+([A-Za-z0-9dhmsw-]+|-)"
        )

    def _parse_size(self, val: str, unit: str) -> int:
        multiplier = 1
        unit = unit.lower().replace("i", "")  # handle MiB vs MB
        if unit.startswith("k"):
            multiplier = 1024
        elif unit.startswith("m"):
            multiplier = 1024**2
        elif unit.startswith("g"):
            multiplier = 1024**3
        elif unit.startswith("t"):
            multiplier = 1024**4
        return int(float(val) * multiplier)

    def _parse_time(self, time_str: str) -> int:
        if not time_str or time_str == "-":
            return 0
        total_seconds = 0
        matches = re.finditer(r"(\d+)([smhd])", time_str)
        for match in matches:
            val = int(match.group(1))
            unit = match.group(2)
            if unit == "s":
                total_seconds += val
            elif unit == "m":
                total_seconds += val * 60
            elif unit == "h":
                total_seconds += val * 3600
            elif unit == "d":
                total_seconds += val * 86400
        return total_seconds

    async def initialize(
        self, config_path: str = None, remote: str = "gdrive:"
    ) -> bool:
        self._config_path = config_path or os.path.expanduser(
            "~/.config/rclone/rclone.conf"
        )
        self._remote = remote

        try:
            # Check if rclone is available
            process = await asyncio.create_subprocess_exec(
                "rclone",
                "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                version = stdout.decode().split("\n")[0].strip()
                logger.info(f"RClone uploader initialized ({version})")
                return True
            else:
                logger.error("rclone binary not found in PATH")
                return False
        except Exception as e:
            logger.error(f"RClone init error: {e}")
            return False

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        file_path = context.source
        remote = config.get("remote", self._remote)
        dest_path = config.get("dest_path", "")

        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            from core.task import update_task_progress, _task_store

            cmd = ["rclone"]

            if os.path.isdir(file_path):
                dest = f"{remote}:{dest_path}" if dest_path else remote
                if dest_path:
                    # If it's a directory and a dest_path is given, append the folder name to dest path
                    dest = f"{remote}:{os.path.join(dest_path, os.path.basename(file_path))}"
                cmd.extend(["copy", file_path, dest])
            else:
                dest = f"{remote}:{dest_path}" if dest_path else remote
                cmd.extend(
                    [
                        "copyto",
                        file_path,
                        f"{dest}/{os.path.basename(file_path)}"
                        if not dest.endswith(os.path.basename(file_path))
                        and not os.path.isdir(file_path)
                        else dest,
                    ]
                )

            cmd.extend(
                [
                    "--config",
                    self._config_path,
                    "--stats",
                    "1s",
                    "--stats-one-line",
                    "--log-level",
                    "INFO",
                ]
            )

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._active_processes[context.task_id] = process

            last_update = 0

            # rclone --stats outputs to stderr
            while True:
                t = _task_store.get(context.task_id)
                if t and t.status.value == "cancelled":
                    process.terminate()
                    raise Exception("Task cancelled by user")

                line = await process.stderr.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                match = self._stats_regex.search(line_str)
                if match:
                    now = time.time()
                    if now - last_update >= 1.0:
                        groups = match.groups()
                        downloaded = self._parse_size(groups[0], groups[1])
                        total = self._parse_size(groups[2], groups[3])
                        pct = float(groups[4])
                        speed = self._parse_size(groups[5], groups[6])
                        eta = self._parse_time(groups[7])

                        asyncio.create_task(
                            update_task_progress(
                                task_id=context.task_id,
                                stage="Uploading",
                                plugin=self.name,
                                progress=pct,
                                speed=speed,
                                eta=eta,
                                uploaded=downloaded,
                                total=total,
                            )
                        )
                        last_update = now

            await process.wait()
            if context.task_id in self._active_processes:
                del self._active_processes[context.task_id]

            if process.returncode == 0:
                # Assuming success, fetch the link if possible
                try:
                    link_cmd = ["rclone", "link", dest, "--config", self._config_path]
                    link_proc = await asyncio.create_subprocess_exec(
                        *link_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    link_out, _ = await link_proc.communicate()
                    link = (
                        link_out.decode().strip() if link_proc.returncode == 0 else ""
                    )
                except:
                    link = ""

                return PluginResult(
                    success=True,
                    output_path=link or dest,
                    metadata={"source": file_path, "dest": dest, "link": link},
                )
            else:
                # Read stdout/stderr for exact error if we failed
                stderr = (
                    (await process.stderr.read()).decode().strip()
                    if hasattr(process.stderr, "read")
                    else "Unknown error"
                )
                return PluginResult(
                    success=False,
                    error=f"RClone failed with exit code {process.returncode}",
                )

        except Exception as e:
            if context.task_id in self._active_processes:
                try:
                    self._active_processes[context.task_id].terminate()
                except:
                    pass
                del self._active_processes[context.task_id]

            logger.error(f"RClone upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _run_command(self, cmd: list) -> tuple:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode(), stderr.decode()

    async def copy(self, source: str, dest: str) -> bool:
        cmd = ["rclone", "copyto", source, dest, "--config", self._config_path]
        ret, _, _ = await self._run_command(cmd)
        return ret == 0

    async def move(self, source: str, dest: str) -> bool:
        cmd = ["rclone", "moveto", source, dest, "--config", self._config_path]
        ret, _, _ = await self._run_command(cmd)
        return ret == 0

    async def delete(self, remote_path: str) -> bool:
        cmd = ["rclone", "purge", remote_path, "--config", self._config_path]
        ret, _, _ = await self._run_command(cmd)
        return ret == 0

    async def list_remotes(self) -> list:
        cmd = ["rclone", "listremotes", "--config", self._config_path]
        ret, stdout, _ = await self._run_command(cmd)
        if ret == 0:
            return [r.strip() for r in stdout.split("\n") if r]
        return []

    async def list_files(self, remote_path: str) -> list:
        cmd = ["rclone", "lsjson", remote_path, "--config", self._config_path]
        ret, stdout, _ = await self._run_command(cmd)
        if ret == 0:
            import json

            try:
                return json.loads(stdout)
            except:
                pass
        return []

    async def size(self, remote_path: str) -> dict:
        cmd = ["rclone", "size", remote_path, "--config", self._config_path]
        ret, stdout, _ = await self._run_command(cmd)
        data = {}
        if ret == 0:
            lines = stdout.split("\n")
            for line in lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    data[key.strip()] = val.strip()
        return data

    async def link(self, remote_path: str) -> str:
        cmd = ["rclone", "link", remote_path, "--config", self._config_path]
        ret, stdout, _ = await self._run_command(cmd)
        if ret == 0:
            return stdout.strip()
        return None

    async def mkdir(self, remote_path: str) -> bool:
        cmd = ["rclone", "mkdir", remote_path, "--config", self._config_path]
        ret, _, _ = await self._run_command(cmd)
        return ret == 0

    async def sync(self, source: str, dest: str) -> bool:
        cmd = ["rclone", "sync", source, dest, "--config", self._config_path]
        ret, _, _ = await self._run_command(cmd)
        return ret == 0
