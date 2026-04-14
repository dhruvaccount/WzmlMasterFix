import asyncio
import logging
import os
import re
from typing import Any, Optional
from secrets import token_hex

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.mega_downloader")

async def cmd_exec(cmd, shell=False):
    if shell:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    stdout, stderr = await proc.communicate()
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode

class MegaDownloader(DownloaderPlugin):
    name = "mega"
    plugin_type = "downloader"

    def __init__(self):
        self._sid = None
        self._logged_in = False
        self._gid = None
        self._process = None
        self._cancel_requested = False

    async def initialize(self, email: str = None, password: str = None) -> bool:
        try:
            if email and password:
                stdout, stderr, ret = await cmd_exec(["mega-login", email, password])
                if ret == 0 or "Already logged in" in stdout:
                    self._logged_in = True
                    logger.info("Mega initialized and logged in")
                    return True
                else:
                    logger.error(f"Mega login failed: {stderr}")
                    return False
            else:
                logger.info("Mega initialized (anonymous)")
                return True
        except Exception as e:
            logger.error(f"Mega init error: {e}")
            return False

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")

        if "mega.nz" not in url.lower():
            return PluginResult(success=False, error="Not a Mega link")

        self._gid = token_hex(5)
        temp_path = f"/wzml_{self._gid}"
        self._cancel_requested = False

        try:
            from core.task import update_task_progress, get_task
            
            if self._logged_in:
                await cmd_exec(["mega-mkdir", temp_path])
                stdout, stderr, ret = await cmd_exec(["mega-import", url, temp_path])
                if ret != 0:
                    return PluginResult(success=False, error=f"Mega import failed: {stderr}")

                # Get name
                stdout, _, ret = await cmd_exec(["mega-ls", "-l", temp_path])
                name = f"MEGA_Download_{self._gid}"
                if stdout:
                    lines = [line for line in stdout.strip().split("\n") if line.strip()]
                    for line in lines:
                        match = re.search(r"\s(\d+|-)\s+\S+\s+\d{2}:\d{2}:\d{2}\s+(.*)$", line)
                        if match:
                            name = match.group(2).strip()
                            break
                            
                target_node = f"{temp_path}/{name}"
            else:
                name = f"MEGA_Download_{self._gid}"
                target_node = url

            os.makedirs(output_path, exist_ok=True)
            self._process = await asyncio.create_subprocess_exec(
                "mega-get", target_node, output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            start_time = time.time()
            last_update = start_time
            downloaded = 0
            total = 0

            while True:
                # Check cancellation
                t = await get_task(context.task_id)
                if t and t.status.value == "cancelled" or self._cancel_requested:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                    return PluginResult(success=False, error="Task cancelled by user")

                try:
                    line_bytes = await asyncio.wait_for(self._process.stdout.readuntil(b"\r"), timeout=2.0)
                    line = line_bytes.decode().strip()
                    
                    multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "B": 1}
                    match = re.search(r"\(([\d\.]+)/([\d\.]+)\s([KMGT]?B)", line)
                    if match:
                        dl_val = float(match.group(1))
                        total_val = float(match.group(2))
                        unit_char = (match.group(3))[0].upper()
                        mult = multipliers.get(unit_char, 1)
                        
                        downloaded = int(dl_val * mult)
                        total = int(total_val * mult)
                        
                    now = time.time()
                    if now - last_update > 1.0 and total > 0:
                        speed = downloaded / (now - start_time)
                        eta = int((total - downloaded) / speed) if speed > 0 else 0
                        pct = (downloaded / total) * 100
                        
                        await update_task_progress(
                            task_id=context.task_id,
                            stage="Downloading",
                            plugin=self.name,
                            progress=pct,
                            speed=speed,
                            eta=eta,
                            downloaded=downloaded,
                            total=total,
                        )
                        last_update = now
                        
                except asyncio.TimeoutError:
                    if self._process.returncode is not None:
                        break
                except asyncio.IncompleteReadError:
                    break
                except Exception as e:
                    logger.error(f"Mega parse error: {e}")
                    break

            await self._process.wait()

            if self._logged_in:
                await cmd_exec(["mega-rm", "-r", "-f", temp_path])

            if self._process.returncode == 0:
                return PluginResult(
                    success=True,
                    output_path=os.path.join(output_path, name),
                    metadata={"name": name, "size": total},
                )
            else:
                return PluginResult(success=False, error=f"MegaCMD exited with {self._process.returncode}")

        except Exception as e:
            logger.error(f"Mega download error: {e}")
            if self._logged_in:
                await cmd_exec(["mega-rm", "-r", "-f", temp_path])
            return PluginResult(success=False, error=str(e))

    async def get_status(self, url: str = None) -> dict:
        return {}

    async def cancel(self) -> bool:
        self._cancel_requested = True
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
        return True

    async def pause(self) -> bool:
        return False

    async def resume(self) -> bool:
        return False
