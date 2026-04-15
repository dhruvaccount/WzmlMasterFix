import asyncio
import logging
import os
import time
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.splitter_processor")


class SplitterProcessor(ProcessorPlugin):
    name = "splitter"
    plugin_type = "processor"

    def __init__(self):
        self._chunk_size = 10 * 1024 * 1024

    async def initialize(self, chunk_size: int = 10 * 1024 * 1024) -> bool:
        self._chunk_size = chunk_size
        logger.info(f"Splitter initialized: chunk_size={chunk_size}")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        chunk_size = config.get("chunk_size", self._chunk_size)
        output_dir = config.get("output_dir", os.path.dirname(source))

        if not os.path.exists(source):
            return PluginResult(success=False, error="File not found")

        try:
            file_size = os.path.getsize(source)
            num_parts = (file_size + chunk_size - 1) // chunk_size

            if num_parts <= 1:
                return PluginResult(
                    success=True,
                    output_path=source,
                    metadata={"parts": 1, "reason": "file smaller than chunk size"},
                )

            from core.task import update_task_progress

            await update_task_progress(
                task_id=context.task_id,
                stage="Splitting",
                plugin=self.name,
                progress=0.0,
            )

            parts = await self._split_file(context, source, output_dir, chunk_size)

            return PluginResult(
                success=True,
                output_paths=parts,
                metadata={"parts": len(parts), "chunk_size": chunk_size},
            )

        except Exception as e:
            logger.error(f"Split error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _split_file(
        self, context: PluginContext, source: str, output_dir: str, chunk_size: int
    ) -> list:
        from core.task import update_task_progress, _task_store

        file_size = os.path.getsize(source)
        base_name = os.path.basename(source)
        name, ext = os.path.splitext(base_name)

        loop = asyncio.get_running_loop()
        start_time = time.time()
        last_update = start_time

        def _split():
            nonlocal last_update
            local_parts = []

            with open(source, "rb") as f:
                part_num = 1
                bytes_read = 0
                while True:
                    t = _task_store.get(context.task_id)
                    if t and t.status.value == "cancelled":
                        raise Exception("Task cancelled by user")

                    part_name = f"{name}.part{part_num:03d}{ext}"
                    part_path = os.path.join(output_dir, part_name)

                    bytes_in_part = 0
                    with open(part_path, "wb") as part_file:
                        while bytes_in_part < chunk_size:
                            t = _task_store.get(context.task_id)
                            if t and t.status.value == "cancelled":
                                raise Exception("Task cancelled by user")

                            chunk_to_read = min(
                                1024 * 1024 * 5, chunk_size - bytes_in_part
                            )
                            chunk = f.read(chunk_to_read)
                            if not chunk:
                                break

                            part_file.write(chunk)
                            bytes_in_part += len(chunk)
                            bytes_read += len(chunk)

                            now = time.time()
                            if now - last_update >= 1.0:
                                pct = (
                                    (bytes_read / file_size) * 100.0 if file_size else 0
                                )
                                asyncio.run_coroutine_threadsafe(
                                    update_task_progress(
                                        task_id=context.task_id,
                                        stage="Splitting",
                                        plugin=self.name,
                                        progress=pct,
                                    ),
                                    loop,
                                )
                                last_update = now

                    if bytes_in_part == 0:
                        if os.path.exists(part_path):
                            os.remove(part_path)
                        break

                    local_parts.append(part_path)
                    part_num += 1

            return local_parts

        return await asyncio.to_thread(_split)

    async def join_files(self, parts: list, output: str) -> bool:
        def _join():
            with open(output, "wb") as out_file:
                for part in sorted(parts):
                    with open(part, "rb") as in_file:
                        while True:
                            chunk = in_file.read(1024 * 1024 * 5)
                            if not chunk:
                                break
                            out_file.write(chunk)
            return True

        try:
            return await asyncio.to_thread(_join)
        except Exception as e:
            logger.error(f"Join error: {e}")
            return False

    async def split_by_count(
        self, context: PluginContext, source: str, count: int
    ) -> list:
        file_size = os.path.getsize(source)
        chunk_size = file_size // count

        return await self._split_file(
            context, source, os.path.dirname(source), chunk_size
        )
