import asyncio
import logging
import os
import json
import base64
import time
import random
import shutil
import re
from typing import Any, Optional
from secrets import token_hex

from plugins.base import DownloaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

logger = logging.getLogger("wzml.jd_downloader")

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

class JDownloaderDownloader(DownloaderPlugin):
    name = "jd"
    plugin_type = "downloader"

    def __init__(self):
        self._device = None
        self._device_id = None
        self._connected = False
        self._package_ids = []
        self._gid = None
        self._jd_task = None
        self._device_name = ""

    async def _write_config(self, filepath, data):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)

    async def _boot_daemon(self, email: str, password: str):
        await cmd_exec(["pkill", "-9", "-f", "java"])
        
        self._device_name = f"{random.randint(0, 1000)}@WZML-X"
        logger.info(f"Starting JDownloader... Device: {self._device_name}")
        
        jdata = {
            "autoconnectenabledv2": True,
            "password": password,
            "devicename": self._device_name,
            "email": email,
        }
        
        remote_data = {
            "localapiserverheaderaccesscontrollalloworigin": "",
            "deprecatedapiport": 3128,
            "localapiserverheaderxcontenttypeoptions": "nosniff",
            "localapiserverheaderxframeoptions": "DENY",
            "externinterfaceenabled": True,
            "deprecatedapilocalhostonly": True,
            "localapiserverheaderreferrerpolicy": "no-referrer",
            "deprecatedapienabled": True,
            "localapiserverheadercontentsecuritypolicy": "default-src 'self'",
            "jdanywhereapienabled": True,
            "externinterfacelocalhostonly": False,
            "localapiserverheaderxxssprotection": "1; mode=block",
        }
        
        await self._write_config("/JDownloader/cfg/org.jdownloader.api.myjdownloader.MyJDownloaderSettings.json", jdata)
        await self._write_config("/JDownloader/cfg/org.jdownloader.api.RemoteAPIConfig.json", remote_data)
        
        if not os.path.exists("/JDownloader/JDownloader.jar"):
            pattern = re.compile(r"JDownloader\.jar\.backup\.\d$")
            try:
                for filename in os.listdir("/JDownloader"):
                    if pattern.match(filename):
                        os.rename(f"/JDownloader/{filename}", "/JDownloader/JDownloader.jar")
                        break
            except Exception:
                pass
            shutil.rmtree("/JDownloader/update", ignore_errors=True)
            shutil.rmtree("/JDownloader/tmp", ignore_errors=True)

        cmd = "cpulimit -l 20 -- java -Xms256m -Xmx500m -Dsun.jnu.encoding=UTF-8 -Dfile.encoding=UTF-8 -Djava.awt.headless=true -jar /JDownloader/JDownloader.jar"
        
        async def _runner():
            while True:
                _, __, code = await cmd_exec(cmd, shell=True)
                if code == -9:
                    break
                await asyncio.sleep(2)

        self._jd_task = asyncio.create_task(_runner())

    async def initialize(
        self, email: str = None, password: str = None, device_id: str = None
    ) -> bool:
        try:
            from myjd import MyJdApi

            if not email or not password:
                logger.warning("JD credentials not provided, skipping initialization.")
                return False

            await self._boot_daemon(email, password)

            myjd = MyJdApi(email, password)
            
            # Wait for JD to boot and connect
            for _ in range(15):
                if await myjd.connect():
                    break
                await asyncio.sleep(2)
            else:
                logger.error("Failed to connect to MyJD after booting.")
                return False

            # Wait for device to be online
            for _ in range(10):
                devices = await myjd.list_devices()
                device = next((d for d in devices if d.get("name") == self._device_name), None)
                if device:
                    device_id = device.get("id")
                    break
                await asyncio.sleep(2)

            self._device = await myjd.get_device(device_id) if device_id else None
            
            if self._device:
                self._device_id = device_id
                self._connected = True
                logger.info(f"JDownloader initialized: {self._device_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"JDownloader init error: {e}")
            self._connected = False
            return False

    async def is_connected(self) -> bool:
        return self._connected

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        path = config.get("path", "/tmp/downloads")
        package_name = config.get("package_name")
        password = config.get("password")

        if not self._connected:
            return PluginResult(success=False, error="JDownloader not connected")

        try:
            self._gid = token_hex(5)

            links = [{"links": url}]
            if package_name:
                links[0]["packageName"] = package_name
            if password:
                links[0]["password"] = password

            await self._device.linkgrabber.add_links(links)

            await asyncio.sleep(1)

            await self._device.linkgrabber.collect()

            packages = await self._device.linkgrabber.query_packages([{"saveTo": True}])
            package_ids = [
                p["uuid"] for p in packages if p.get("saveTo", "").startswith(path)
            ]

            if not package_ids:
                return PluginResult(success=False, error="No packages found")

            self._package_ids = package_ids

            await self._device.linkgrabber.set_download_directory(path, package_ids)

            await self._device.linkgrabber.move_to_downloadlist(package_ids)

            await self._device.downloads.force_download(package_ids)

            result = {
                "gid": self._gid,
                "package_ids": package_ids,
                "url": url,
                "path": path,
            }

            return PluginResult(
                success=True,
                output_path=path,
                metadata=result,
            )

        except Exception as e:
            logger.error(f"JDownloader download error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_status(self) -> dict:
        if not self._connected or not self._package_ids:
            return {}

        try:
            packages = await self._device.downloads.query_packages(
                [{"packageUUIDs": self._package_ids}]
            )
            if packages:
                p = packages[0]
                return {
                    "name": p.get("name"),
                    "status": p.get("status"),
                    "bytesTotal": p.get("bytesTotal"),
                    "bytesLoaded": p.get("bytesLoaded"),
                    "speed": p.get("speed"),
                }
        except Exception as e:
            logger.error(f"JDownloader status error: {e}")
            return {"error": str(e)}

    async def pause(self) -> bool:
        if not self._connected or not self._package_ids:
            return False
        try:
            await self._device.downloads.pause(self._package_ids)
            return True
        except Exception as e:
            logger.error(f"JDownloader pause error: {e}")
            return False

    async def resume(self) -> bool:
        if not self._connected or not self._package_ids:
            return False
        try:
            await self._device.downloads.force_download(self._package_ids)
            return True
        except Exception as e:
            logger.error(f"JDownloader resume error: {e}")
            return False

    async def cancel(self) -> bool:
        if not self._connected or not self._package_ids:
            return False
        try:
            await self._device.linkgrabber.remove_links(self._package_ids)
            return True
        except Exception as e:
            logger.error(f"JDownloader cancel error: {e}")
            return False

    async def delete(self) -> bool:
        return await self.cancel()

    async def get_packages(self) -> list:
        if not self._connected:
            return []
        try:
            return await self._device.downloads.query_packages([{}])
        except Exception as e:
            logger.error(f"JDownloader packages error: {e}")
            return []

    async def get_links(self) -> list:
        if not self._connected:
            return []
        try:
            return await self._device.linkgrabber.query_links([{}])
        except Exception as e:
            logger.error(f"JDownloader links error: {e}")
            return []

    async def clear_linkgrabber(self) -> bool:
        if not self._connected:
            return False
        try:
            await self._device.linkgrabber.clear_list()
            return True
        except Exception as e:
            logger.error(f"JDownloader clear error: {e}")
            return False

    async def set_device(self, device_id: str) -> bool:
        if not self._connected:
            return False
        try:
            self._device = await self._myjd.get_device(device_id)
            self._device_id = device_id
            return True
        except Exception as e:
            logger.error(f"JDownloader set_device error: {e}")
            return False

    async def get_devices(self) -> list:
        if not self._connected:
            return []
        try:
            return await self._myjd.get_devices()
        except Exception as e:
            logger.error(f"JDownloader devices error: {e}")
            return []
