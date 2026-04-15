import asyncio
import logging
import os
import zipfile
import tarfile
import time
import re
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.extractor")


class ExtractorProcessor(ProcessorPlugin):
    name = "extractor"
    plugin_type = "processor"

    def __init__(self):
        self._password = None
        self._active_processes = {}
        # Progress matchers for 7z
        self._7z_progress_regex = re.compile(r"^\s*(\d+)%\s*-")

    async def initialize(self, password: str = None) -> bool:
        self._password = password
        logger.info("Extractor initialized")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output_path = config.get("output_path", os.path.dirname(source) or ".")
        password = config.get("password", self._password)

        if not os.path.exists(source):
            return PluginResult(success=False, error="File not found")

        # Create output directory if it doesn't exist
        os.makedirs(output_path, exist_ok=True)

        from core.task import update_task_progress

        await update_task_progress(
            task_id=context.task_id, stage="Extracting", plugin=self.name, progress=0.0
        )

        try:
            extracted_files = []

            # 7z and rar use subprocess, zip and tar use python libs
            if (
                source.endswith(".7z")
                or source.endswith(".rar")
                or source.endswith(".001")
            ):
                result = await self._extract_cli(context, source, output_path, password)
                extracted_files = result.get("files", [])
            elif source.endswith(".zip"):
                result = await self._extract_zip(context, source, output_path, password)
                extracted_files = result.get("files", [])
            elif source.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                result = await self._extract_tar(context, source, output_path)
                extracted_files = result.get("files", [])
            else:
                # Try 7z as fallback for unknown archives
                result = await self._extract_cli(context, source, output_path, password)
                extracted_files = result.get("files", [])

            await update_task_progress(
                task_id=context.task_id,
                stage="Extracting",
                plugin=self.name,
                progress=100.0,
            )

            return PluginResult(
                success=True,
                output_path=output_path,
                output_paths=extracted_files,
                metadata={"count": len(extracted_files)},
            )

        except Exception as e:
            if context.task_id in self._active_processes:
                try:
                    self._active_processes[context.task_id].terminate()
                except:
                    pass
                del self._active_processes[context.task_id]

            logger.error(f"Extraction error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _extract_cli(
        self,
        context: PluginContext,
        archive_path: str,
        output_path: str,
        password: str = None,
    ) -> dict:
        from core.task import update_task_progress, _task_store

        binary = "7z"  # or unrar, but 7z handles rar well enough if installed
        if archive_path.endswith(".rar"):
            # Try unrar first, fallback to 7z
            binary = "unrar" if os.system("unrar --version >nul 2>&1") == 0 else "7z"

        if binary == "7z":
            cmd = [
                "7z",
                "x",
                archive_path,
                f"-o{output_path}",
                "-y",
                "-bsp1",
            ]  # -bsp1 enables progress on stdout
            if password:
                cmd.append(f"-p{password}")
        else:
            cmd = ["unrar", "x", archive_path, output_path, "-y"]
            if password:
                cmd.insert(2, f"-p{password}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_processes[context.task_id] = process

        last_update = 0
        while True:
            t = _task_store.get(context.task_id)
            if t and t.status.value == "cancelled":
                process.terminate()
                raise Exception("Task cancelled by user")

            line = await process.stdout.readline()
            if not line:
                break

            # 7z progress looks like: " 12% - 13 files"
            if binary == "7z":
                line_str = line.decode().strip()
                match = self._7z_progress_regex.search(line_str)
                if match:
                    now = time.time()
                    if now - last_update >= 1.0:
                        pct = float(match.group(1))
                        asyncio.create_task(
                            update_task_progress(
                                task_id=context.task_id,
                                stage="Extracting (7z)",
                                plugin=self.name,
                                progress=pct,
                            )
                        )
                        last_update = now

        stdout, stderr = await process.communicate()
        if context.task_id in self._active_processes:
            del self._active_processes[context.task_id]

        if process.returncode == 0:
            # We don't parse files list from 7z output as it can be huge, just return empty list to let caller handle
            return {"files": [], "path": output_path}
        else:
            raise Exception(f"{binary} failed: {stderr.decode()}")

    async def _extract_zip(
        self,
        context: PluginContext,
        archive_path: str,
        output_path: str,
        password: str = None,
    ) -> dict:
        from core.task import update_task_progress, _task_store

        def _extract():
            files = []
            with zipfile.ZipFile(archive_path, "r") as zf:
                if password:
                    zf.setpassword(password.encode() if password else None)

                info_list = zf.infolist()
                total_files = len(info_list)

                for i, info in enumerate(info_list):
                    # Check cancellation
                    t = _task_store.get(context.task_id)
                    if t and t.status.value == "cancelled":
                        raise Exception("Task cancelled by user")

                    zf.extract(info, output_path)
                    files.append(info.filename)

                    if i % max(1, total_files // 100) == 0:
                        asyncio.run_coroutine_threadsafe(
                            update_task_progress(
                                task_id=context.task_id,
                                stage="Extracting (Zip)",
                                plugin=self.name,
                                progress=(i / total_files) * 100.0,
                            ),
                            asyncio.get_running_loop(),
                        )
            return {"files": files, "path": output_path}

        return await asyncio.to_thread(_extract)

    async def _extract_tar(
        self, context: PluginContext, archive_path: str, output_path: str
    ) -> dict:
        from core.task import update_task_progress, _task_store

        def _extract():
            files = []
            with tarfile.open(archive_path, "r") as tf:
                members = tf.getmembers()
                total_files = len(members)

                for i, member in enumerate(members):
                    # Check cancellation
                    t = _task_store.get(context.task_id)
                    if t and t.status.value == "cancelled":
                        raise Exception("Task cancelled by user")

                    tf.extract(member, output_path)
                    files.append(member.name)

                    if i % max(1, total_files // 100) == 0:
                        asyncio.run_coroutine_threadsafe(
                            update_task_progress(
                                task_id=context.task_id,
                                stage="Extracting (Tar)",
                                plugin=self.name,
                                progress=(i / total_files) * 100.0,
                            ),
                            asyncio.get_running_loop(),
                        )
            return {"files": files, "path": output_path}

        return await asyncio.to_thread(_extract)
