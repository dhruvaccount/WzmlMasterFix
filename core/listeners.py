import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from core.task import Task, TaskStatus
from core.queue import get_queue_manager


logger = logging.getLogger("wzml.listener")


class ListenerType(Enum):
    DOWNLOAD = "download"
    UPLOAD = "upload"
    PROCESS = "process"


class TaskListener:
    def __init__(self):
        self._handlers = {}
        self._running = False
        self._queue_manager = get_queue_manager()

    def register_handler(self, event: str, handler: Callable):
        self._handlers[event] = handler

    async def emit(self, event: str, *args, **kwargs):
        handler = self._handlers.get(event)
        if handler:
            await handler(*args, **kwargs)


class Aria2Listener(TaskListener):
    def __init__(self):
        super().__init__()
        self._gids = {}
        self._callbacks = {}

    async def start(self):
        self._running = True
        logger.info("Aria2 listener started")

        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        logger.info("Aria2 listener stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._check_aria2_status()
            except Exception as e:
                logger.error(f"Aria2 poll error: {e}")

            await asyncio.sleep(5)

    async def _check_aria2_status(self):
        for gid, task_id in list(self._gids.items()):
            try:
                task = await get_queue_manager()._running.get(task_id)
                if not task:
                    continue

                await self.emit("download_complete", task_id, {"gid": gid})

                del self._gids[gid]
            except:
                pass

    def add_download(self, task: Task, gid: str):
        self._gids[gid] = task.id

    def remove_download(self, gid: str):
        if gid in self._gids:
            del self._gids[gid]

    async def on_download_start(self, task_id: str, info: dict):
        await self.emit("download_start", task_id, info)
        logger.info(f"Aria2 download started: {task_id}")

    async def on_download_complete(self, task_id: str, info: dict):
        await self.emit("download_complete", task_id, info)
        logger.info(f"Aria2 download completed: {task_id}")

    async def on_download_error(self, task_id: str, error: str):
        await self.emit("download_error", task_id, error)
        logger.error(f"Aria2 download error: {task_id} - {error}")


class QBitListener(TaskListener):
    def __init__(self):
        super().__init__()
        self._torrents = {}
        self._hashes = {}

    async def start(self):
        self._running = True
        logger.info("QBit listener started")

        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        logger.info("QBit listener stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._check_torrent_status()
            except Exception as e:
                logger.error(f"QBit poll error: {e}")

            await asyncio.sleep(5)

    async def _check_torrent_status(self):
        for hash_info, task_id in list(self._hashes.items()):
            try:
                task = await get_queue_manager()._running.get(task_id)
                if not task:
                    continue

                await self.emit("torrent_complete", task_id, {"hash": hash_info})

                del self._hashes[hash_info]
            except:
                pass

    def add_torrent(self, task: Task, hash_info: str):
        self._hashes[hash_info] = task.id
        self._torrents[task.id] = hash_info

    def remove_torrent(self, hash_info: str):
        if hash_info in self._hashes:
            task_id = self._hashes[hash_info]
            del self._hashes[hash_info]
            if task_id in self._torrents:
                del self._torrents[task_id]

    async def on_torrent_added(self, task_id: str, info: dict):
        await self.emit("torrent_added", task_id, info)

    async def on_torrent_complete(self, task_id: str, info: dict):
        await self.emit("torrent_complete", task_id, info)

    async def on_torrent_error(self, task_id: str, error: str):
        await self.emit("torrent_error", task_id, error)


class MegaListener(TaskListener):
    def __init__(self):
        super().__init__()
        self._downloads = {}

    async def start(self):
        self._running = True
        logger.info("Mega listener started")

    async def stop(self):
        self._running = False
        logger.info("Mega listener stopped")

    def add_download(self, task: Task, handle):
        self._downloads[task.id] = handle
        asyncio.create_task(self._monitor_download(task.id, handle))

    async def _monitor_download(self, task_id: str, handle):
        while handle and not handle.is_finished:
            await asyncio.sleep(1)

        if handle.is_complete:
            await self.emit("download_complete", task_id, {})
        else:
            await self.emit("download_error", task_id, handle.error)

    async def on_download_start(self, task_id: str):
        await self.emit("download_start", task_id, {})

    async def on_download_complete(self, task_id: str):
        await self.emit("download_complete", task_id, {})

    async def on_download_error(self, task_id: str, error: str):
        await self.emit("download_error", task_id, error)


class JDListener(TaskListener):
    def __init__(self):
        super().__init__()
        self._packages = {}

    async def start(self):
        self._running = True
        logger.info("JD listener started")

        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        logger.info("JD listener stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._check_packages()
            except Exception as e:
                logger.error(f"JD poll error: {e}")

            await asyncio.sleep(10)

    async def _check_packages(self):
        for pkg_id, task_id in list(self._packages.items()):
            try:
                task = await get_queue_manager()._running.get(task_id)
                if not task:
                    continue

                await self.emit("package_complete", task_id, {"package_id": pkg_id})

                del self._packages[pkg_id]
            except:
                pass

    def add_package(self, task: Task, package_id: str):
        self._packages[package_id] = task.id

    def remove_package(self, package_id: str):
        if package_id in self._packages:
            del self._packages[package_id]

    async def on_package_added(self, task_id: str, info: dict):
        await self.emit("package_added", task_id, info)

    async def on_package_complete(self, task_id: str, info: dict):
        await self.emit("package_complete", task_id, info)


class NZBListener(TaskListener):
    def __init__(self):
        super().__init__()
        self._jobs = {}

    async def start(self):
        self._running = True
        logger.info("NZB listener started")

        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        logger.info("NZB listener stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._check_jobs()
            except Exception as e:
                logger.error(f"NZB poll error: {e}")

            await asyncio.sleep(5)

    async def _check_jobs(self):
        for job_id, task_id in list(self._jobs.items()):
            try:
                task = await get_queue_manager()._running.get(task_id)
                if not task:
                    continue

                await self.emit("job_complete", task_id, {"job_id": job_id})

                del self._jobs[job_id]
            except:
                pass

    def add_job(self, task: Task, job_id: str):
        self._jobs[job_id] = task.id

    def remove_job(self, job_id: str):
        if job_id in self._jobs:
            del self._jobs[job_id]

    async def on_job_added(self, task_id: str, info: dict):
        await self.emit("job_added", task_id, info)

    async def on_job_complete(self, task_id: str, info: dict):
        await self.emit("job_complete", task_id, info)


class DirectListener(TaskListener):
    def __init__(self):
        super().__init__()

    async def start(self):
        self._running = True
        logger.info("Direct listener started")

    async def stop(self):
        self._running = False
        logger.info("Direct listener stopped")

    async def on_download_start(self, task_id: str, info: dict):
        await self.emit("download_start", task_id, info)

    async def on_download_progress(self, task_id: str, progress: int):
        await self.emit("download_progress", task_id, progress)

    async def on_download_complete(self, task_id: str, info: dict):
        await self.emit("download_complete", task_id, info)

    async def on_download_error(self, task_id: str, error: str):
        await self.emit("download_error", task_id, error)


class TaskListenerManager(TaskListener):
    def __init__(self):
        super().__init__()
        self._listeners = {
            "aria2": Aria2Listener(),
            "qbit": QBitListener(),
            "mega": MegaListener(),
            "jd": JDListener(),
            "nzb": NZBListener(),
            "direct": DirectListener(),
        }
        self._map_events()

    def _map_events(self):
        for name, listener in self._listeners.items():
            listener.register_handler("download_start", self._on_download_start)
            listener.register_handler("download_progress", self._on_download_progress)
            listener.register_handler("download_complete", self._on_download_complete)
            listener.register_handler("upload_start", self._on_upload_start)
            listener.register_handler("upload_progress", self._on_upload_progress)
            listener.register_handler("upload_complete", self._on_upload_complete)

            # Map specific plugin events
            listener.register_handler("torrent_added", self._on_download_start)
            listener.register_handler("torrent_progress", self._on_download_progress)
            listener.register_handler("torrent_complete", self._on_download_complete)

            listener.register_handler("package_added", self._on_download_start)
            listener.register_handler("package_progress", self._on_download_progress)
            listener.register_handler("package_complete", self._on_download_complete)

            listener.register_handler("job_added", self._on_download_start)
            listener.register_handler("job_progress", self._on_download_progress)
            listener.register_handler("job_complete", self._on_download_complete)

    async def _on_download_start(self, task_id: str, info: dict = None, **kwargs):
        from core.task import update_task_progress

        try:
            await update_task_progress(
                task_id, stage="Downloading", plugin="listener", progress=0.0
            )
        except Exception:
            pass

    async def _on_download_progress(
        self,
        task_id: str,
        progress: float,
        speed: float = 0.0,
        eta: int = 0,
        downloaded: int = 0,
        total: int = 0,
        **kwargs,
    ):
        from core.task import update_task_progress

        try:
            await update_task_progress(
                task_id,
                stage="Downloading",
                plugin="listener",
                progress=float(progress),
                speed=float(speed),
                eta=int(eta),
                downloaded=int(downloaded),
                total=int(total),
            )
        except Exception:
            pass

    async def _on_download_complete(self, task_id: str, info: dict = None, **kwargs):
        from core.task import update_task_progress

        try:
            await update_task_progress(
                task_id, stage="Downloaded", plugin="listener", progress=100.0
            )
        except Exception:
            pass

    async def _on_upload_start(self, task_id: str, info: dict = None, **kwargs):
        from core.task import update_task_progress

        try:
            await update_task_progress(
                task_id, stage="Uploading", plugin="listener", progress=0.0
            )
        except Exception:
            pass

    async def _on_upload_progress(
        self,
        task_id: str,
        progress: float,
        speed: float = 0.0,
        eta: int = 0,
        uploaded: int = 0,
        total: int = 0,
        **kwargs,
    ):
        from core.task import update_task_progress

        try:
            await update_task_progress(
                task_id,
                stage="Uploading",
                plugin="listener",
                progress=float(progress),
                speed=float(speed),
                eta=int(eta),
                uploaded=int(uploaded),
                total=int(total),
            )
        except Exception:
            pass

    async def _on_upload_complete(self, task_id: str, info: dict = None, **kwargs):
        from core.task import update_task_progress

        try:
            await update_task_progress(
                task_id, stage="Uploaded", plugin="listener", progress=100.0
            )
        except Exception:
            pass

    async def start_all(self):
        for name, listener in self._listeners.items():
            try:
                await listener.start()
            except Exception as e:
                logger.error(f"Failed to start listener {name}: {e}")

    async def stop_all(self):
        for name, listener in self._listeners.items():
            try:
                await listener.stop()
            except Exception as e:
                logger.error(f"Failed to stop listener {name}: {e}")

    def get_listener(self, name: str) -> Optional[TaskListener]:
        return self._listeners.get(name)


_listener_manager = None


def get_listener_manager() -> TaskListenerManager:
    global _listener_manager
    if _listener_manager is None:
        _listener_manager = TaskListenerManager()
    return _listener_manager


async def start_listeners():
    manager = get_listener_manager()
    await manager.start_all()


async def stop_listeners():
    manager = get_listener_manager()
    await manager.stop_all()
