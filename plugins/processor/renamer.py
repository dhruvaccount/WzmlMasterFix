import asyncio
import logging
import os
import re
import shutil
from typing import Any, Optional

from plugins.base import ProcessorPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.renamer_processor")


class RenamerProcessor(ProcessorPlugin):
    name = "renamer"
    plugin_type = "processor"

    def __init__(self):
        pass

    async def initialize(self) -> bool:
        logger.info("Renamer initialized")
        return True

    async def process(self, context: PluginContext, config: dict) -> PluginResult:
        source = context.source
        pattern = config.get("pattern", "")
        replacement = config.get("replacement", "")
        new_name = config.get("new_name")
        to_lower = config.get("to_lower", False)
        to_upper = config.get("to_upper", False)
        spaces = config.get("spaces", "_")

        if not os.path.exists(source):
            return PluginResult(success=False, error="File not found")

        try:
            dir_path = os.path.dirname(source)
            base_name = os.path.basename(source)
            name, ext = os.path.splitext(base_name)

            if pattern and replacement is not None:
                new_name = re.sub(pattern, replacement, name)
            elif new_name:
                new_name = new_name
            else:
                new_name = name

            if to_lower:
                new_name = new_name.lower()
            elif to_upper:
                new_name = new_name.upper()

            if spaces:
                new_name = new_name.replace(" ", spaces)

            new_path = os.path.join(dir_path, new_name + ext)

            if new_path != source:
                await asyncio.to_thread(shutil.move, source, new_path)

            return PluginResult(
                success=True,
                output_path=new_path,
                metadata={"original": source, "renamed": new_path},
            )

        except Exception as e:
            logger.error(f"Rename error: {e}")
            return PluginResult(success=False, error=str(e))

    async def batch_rename(self, files: list, pattern: str, replacement: str) -> list:
        results = []

        for file_path in files:
            config = {
                "pattern": pattern,
                "replacement": replacement,
            }
            result = await self.process(PluginContext(source=file_path), config)
            results.append(result)

        return results

    async def add_prefix(self, source: str, prefix: str) -> str:
        dir_path = os.path.dirname(source)
        base_name = os.path.basename(source)
        new_path = os.path.join(dir_path, prefix + base_name)

        await asyncio.to_thread(shutil.move, source, new_path)
        return new_path

    async def add_suffix(self, source: str, suffix: str) -> str:
        dir_path = os.path.dirname(source)
        name, ext = os.path.splitext(os.path.basename(source))
        new_path = os.path.join(dir_path, name + suffix + ext)

        await asyncio.to_thread(shutil.move, source, new_path)
        return new_path

    async def remove_pattern(self, source: str, pattern: str) -> str:
        new_name = re.sub(pattern, "", os.path.basename(source))
        dir_path = os.path.dirname(source)
        new_path = os.path.join(dir_path, new_name)

        await asyncio.to_thread(shutil.move, source, new_path)
        return new_path
