import asyncio
import logging
import os
import subprocess
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

            parts = await self._split_file(source, output_dir, chunk_size)

            return PluginResult(
                success=True,
                output_paths=parts,
                metadata={"parts": len(parts), "chunk_size": chunk_size},
            )

        except Exception as e:
            logger.error(f"Split error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _split_file(self, source: str, output_dir: str, chunk_size: int) -> list:
        parts = []
        base_name = os.path.basename(source)
        name, ext = os.path.splitext(base_name)

        with open(source, "rb") as f:
            part_num = 1
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                part_name = f"{name}.part{part_num:03d}{ext}"
                part_path = os.path.join(output_dir, part_name)

                with open(part_path, "wb") as part_file:
                    part_file.write(chunk)

                parts.append(part_path)
                part_num += 1

        return parts

    async def join_files(self, parts: list, output: str) -> bool:
        try:
            with open(output, "wb") as out_file:
                for part in sorted(parts):
                    with open(part, "rb") as in_file:
                        out_file.write(in_file.read())

            return True
        except Exception as e:
            logger.error(f"Join error: {e}")
            return False

    async def split_by_count(self, source: str, count: int) -> list:
        file_size = os.path.getsize(source)
        chunk_size = file_size // count

        return await self._split_file(source, os.path.dirname(source), chunk_size)
