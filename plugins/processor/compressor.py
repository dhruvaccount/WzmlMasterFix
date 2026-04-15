import asyncio
import logging
import os
import re
import time
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.compressor")


class CompressorProcessor(ProcessorPlugin):
    name = "compressor"
    plugin_type = "processor"

    def __init__(self):
        self._method = "zip"
        self._level = 6
        self._active_processes = {}
        self._7z_progress_regex = re.compile(r"^\s*(\d+)%\s*-")

    async def initialize(self, method: str = "zip", level: int = 6) -> bool:
        self._method = method
        self._level = level
        logger.info(f"Compressor initialized: {method}")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        output_path = config.get("output_path")
        method = config.get("method", self._method)
        level = config.get("level", self._level)
        password = config.get("password")

        if not os.path.exists(source):
            return PluginResult(success=False, error="Source not found")

        try:
            if not output_path:
                output_path = source + f".{method}"

            from core.task import update_task_progress

            await update_task_progress(
                task_id=context.task_id,
                stage="Compressing",
                plugin=self.name,
                progress=0.0,
            )

            result = await self._compress_cli(
                context, source, output_path, method, level, password
            )

            return PluginResult(
                success=True,
                output_path=output_path,
                metadata=result,
            )

        except Exception as e:
            if context.task_id in self._active_processes:
                try:
                    self._active_processes[context.task_id].terminate()
                except:
                    pass
                del self._active_processes[context.task_id]

            logger.error(f"Compression error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _compress_cli(
        self,
        context: PluginContext,
        source: str,
        output_path: str,
        method: str,
        level: int,
        password: str = None,
    ) -> dict:
        from core.task import update_task_progress, _task_store

        fmt = method.lower()
        if fmt in ["tar.gz", "tgz"]:
            return await self._compress_targz(context, source, output_path)

        cmd = ["7z", "a", output_path, source, "-bsp1", "-y"]

        if fmt == "zip":
            cmd.extend(["-tzip", f"-mx={level}"])
        elif fmt == "tar":
            cmd.extend(["-ttar"])
        elif fmt == "7z":
            cmd.extend(["-t7z", f"-mx={level}"])
        else:
            # Fallback assuming zip or supported format
            cmd.extend(["-tzip", f"-mx={level}"])

        if password and fmt in ["zip", "7z"]:
            cmd.append(f"-p{password}")

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

            line_str = line.decode().strip()
            match = self._7z_progress_regex.search(line_str)
            if match:
                now = time.time()
                if now - last_update >= 1.0:
                    pct = float(match.group(1))

                    asyncio.create_task(
                        update_task_progress(
                            task_id=context.task_id,
                            stage=f"Compressing ({fmt})",
                            plugin=self.name,
                            progress=pct,
                        )
                    )
                    last_update = now

        stdout, stderr = await process.communicate()
        if context.task_id in self._active_processes:
            del self._active_processes[context.task_id]

        if process.returncode == 0:
            return {"format": fmt, "size": os.path.getsize(output_path)}
        else:
            raise Exception(f"7z failed: {stderr.decode()}")

    async def _compress_targz(
        self, context: PluginContext, source: str, output: str
    ) -> dict:
        import tarfile
        import gzip
        from core.task import update_task_progress, _task_store

        def _extract():
            output_tar = output.replace(".tar.gz", ".tar").replace(".tgz", ".tar")

            with tarfile.open(output_tar, "w") as tf:
                if os.path.isdir(source):
                    for root, dirs, files in os.walk(source):
                        for file in files:
                            t = _task_store.get(context.task_id)
                            if t and t.status.value == "cancelled":
                                raise Exception("Task cancelled by user")
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, source)
                            tf.add(file_path, arcname=arcname)
                else:
                    tf.add(source, arcname=os.path.basename(source))

            with open(output_tar, "rb") as f_in:
                with gzip.open(output, "wb", compresslevel=9) as f_out:
                    while True:
                        t = _task_store.get(context.task_id)
                        if t and t.status.value == "cancelled":
                            raise Exception("Task cancelled by user")
                        chunk = f_in.read(1024 * 1024 * 5)
                        if not chunk:
                            break
                        f_out.write(chunk)

            os.remove(output_tar)
            return {"format": "tar.gz", "size": os.path.getsize(output)}

        asyncio.create_task(
            update_task_progress(
                task_id=context.task_id,
                stage="Compressing (tar.gz)",
                plugin=self.name,
                progress=50.0,
            )
        )

        return await asyncio.to_thread(_extract)
