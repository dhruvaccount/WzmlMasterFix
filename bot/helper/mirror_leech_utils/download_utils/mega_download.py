import os
from asyncio import Lock as AsyncLock, sleep as asleep
from contextlib import suppress
from secrets import token_hex

from aiofiles.os import makedirs, path as aiopath
from aioshutil import rmtree
from mega import MegaApi, MegaCancelToken

from .... import LOGGER, task_dict, task_dict_lock, user_data
from ....core.config_manager import Config
from ...telegram_helper.message_utils import send_status_message
from ...ext_utils.task_manager import (
    check_running_tasks,
    limit_checker,
    stop_duplicate_check,
)
from ...ext_utils.bot_utils import sync_to_async
from ...listeners.mega_listener import AsyncMega, MegaAppListener, _mega_error_format
from ...mirror_leech_utils.status_utils.mega_status import MegaDownloadStatus
from ...mirror_leech_utils.status_utils.queue_status import QueueStatus


_ACTIVE_MEGA_LINKS = set()
_ACTIVE_MEGA_LINKS_LOCK = AsyncLock()


def _is_folder_link(link: str) -> bool:
    if not link:
        return False
    return "/folder/" in link or "#F!" in link


def _get_subfolder_handle(link: str) -> str | None:
    if not link:
        return None
    parts = link.split("/folder/")
    if len(parts) >= 3:
        return parts[-1].split("#")[0].split("/")[0].split("?")[0]
    parts = link.split("#F!")
    if len(parts) >= 3:
        return parts[-1].split("!")[0].split("/")[0].split("?")[0]
    return None


def _find_child_by_handle(api, parent_node, target_handle):
    if not parent_node or not target_handle:
        return None
    try:
        children = api.getChildren(parent_node)
        if not children:
            return None
        for i in range(children.size()):
            child = children.get(i)
            try:
                if child.getHandle() == target_handle:
                    return child
            except Exception:
                pass
    except Exception as e:
        LOGGER.warning(f"_find_child_by_handle error: {e}")
    return None


def _make_cancel_token():
    if MegaCancelToken is None:
        return None
    try:
        return MegaCancelToken.createInstance()
    except Exception as e:
        LOGGER.error(f"Mega: failed to create cancel token: {e}")
        return None


async def _reserve_link(link: str):
    async with _ACTIVE_MEGA_LINKS_LOCK:
        if link in _ACTIVE_MEGA_LINKS:
            return False
        _ACTIVE_MEGA_LINKS.add(link)
        return True


async def _release_link(link: str):
    async with _ACTIVE_MEGA_LINKS_LOCK:
        _ACTIVE_MEGA_LINKS.discard(link)


async def _cleanup_dir(directory: str):
    if directory and await aiopath.exists(directory):
        await rmtree(directory, ignore_errors=True)


async def add_mega_download(listener, path):
    if Config.DISABLE_MEGA:
        await listener.on_download_error("Mega Link downloads are currently disabled by the Bot Owner.")
        return

    user_dict = user_data.get(listener.user_id, {})
    mega_email = user_dict.get("MEGA_EMAIL") or Config.MEGA_EMAIL
    mega_password = user_dict.get("MEGA_PASSWORD") or Config.MEGA_PASSWORD

    if not await _reserve_link(listener.link):
        await listener.on_download_error("This Mega link is already being downloaded! Wait for it to finish.")
        return

    async_api = None
    mega_base = ""
    try:
        sdk_gid = token_hex(5)
        await makedirs(path, exist_ok=True)
        mega_base = os.path.join(os.path.dirname(path.rstrip("/")), ".mega_sdk", sdk_gid)
        mega_dir = os.path.join(mega_base, "main")
        await makedirs(mega_dir, exist_ok=True)

        async_api = AsyncMega()
        LOGGER.info("Mega: creating main MegaApi")
        async_api.api = api = MegaApi("", mega_dir, "WZML-X", 4)
        LOGGER.info("Mega: creating main listener")
        mega_listener = MegaAppListener(async_api, listener)
        async_api._mega_listener = mega_listener
        LOGGER.info("Mega: addListener main")
        api.addListener(mega_listener)
        api._listener_ref = mega_listener
        LOGGER.info("Mega: addListener main done")

        is_folder = _is_folder_link(listener.link)
        subfolder_handle = _get_subfolder_handle(listener.link)

        if is_folder:
            LOGGER.info("Mega: folder link, using loginToFolder")
            await async_api.loginToFolder(listener.link)
            LOGGER.info("Mega: loginToFolder done")
            if mega_listener.error:
                await listener.on_download_error(_mega_error_format(mega_listener.error))
                return
            LOGGER.info("Mega: fetchNodes for folder tree")
            await async_api.fetchNodes(source="folder")
            LOGGER.info("Mega: fetchNodes done")
            if mega_listener.error:
                await listener.on_download_error(_mega_error_format(mega_listener.error))
                return
            if subfolder_handle:
                node = await sync_to_async(_find_child_by_handle, api, mega_listener.node, subfolder_handle)
                if not node:
                    await listener.on_download_error("Subfolder not found in the MEGA link")
                    return
            else:
                node = mega_listener.node
            mega_listener.public_node = node
            mega_listener._cache_node_data(node)
            try:
                mega_listener._size = api.getSize(node)
            except Exception:
                pass
        else:
            LOGGER.info("Mega: file link")
            if mega_email and mega_password:
                LOGGER.info("Mega: login starting")
                await async_api.login(mega_email, mega_password)
                LOGGER.info("Mega: login done, error=%s", getattr(mega_listener, "error", None))
                if mega_listener.error:
                    await listener.on_download_error(_mega_error_format(mega_listener.error))
                    return
                LOGGER.info("Mega: fetchNodes starting")
                await async_api.fetchNodes()
                LOGGER.info("Mega: fetchNodes done, error=%s", getattr(mega_listener, "error", None))
                if mega_listener.error:
                    await listener.on_download_error(_mega_error_format(mega_listener.error))
                    return
            LOGGER.info("Mega: getPublicNode starting")
            await async_api.getPublicNode(listener.link)
            LOGGER.info("Mega: getPublicNode done")
            node = mega_listener.public_node
            if not node:
                await listener.on_download_error("Failed to resolve MEGA link")
                return

        listener.name = listener.name or mega_listener._name or f"MEGA_Download_{token_hex(5)}"
        listener.size = mega_listener._size
        if not listener.size and node:
            try:
                listener.size = await sync_to_async(api.getSize, node)
            except Exception:
                pass
        gid = token_hex(5)

        msg, button = await stop_duplicate_check(listener)
        if msg:
            await listener.on_download_error(msg, button)
            return

        if limit_exceeded := await limit_checker(listener):
            await listener.on_download_error(limit_exceeded, is_limit=True)
            return

        added_to_queue, event = await check_running_tasks(listener)
        if added_to_queue:
            async with task_dict_lock:
                task_dict[listener.mid] = QueueStatus(listener, gid, "dl")
            await listener.on_download_start()
            if listener.multi <= 1:
                await send_status_message(listener.message)
            await event.wait()
            if listener.is_cancelled:
                return

        async with task_dict_lock:
            task_dict[listener.mid] = MegaDownloadStatus(listener, mega_listener, gid, "dl")

        if added_to_queue:
            await listener.on_download_start()
        else:
            await listener.on_download_start()
            if listener.multi <= 1:
                await send_status_message(listener.message)

        download_path = path
        if _is_folder_link(listener.link):
            download_path = os.path.join(path, listener.name)
            await makedirs(download_path, exist_ok=True)

        for attempt in range(5):
            LOGGER.info("Mega: download attempt %d/5 starting", attempt + 1)
            cancel_token = _make_cancel_token()
            mega_listener._cancel_token = cancel_token
            mega_listener.error = None
            mega_listener.retryable_error = None
            mega_listener._bytes_transferred = 0
            mega_listener._total_downloaded_bytes = 0
            mega_listener._caller_manages_completion = False

            LOGGER.info("Mega: startDownload calling ...")
            await async_api.startDownload(
                node,
                download_path,
                listener.name,
                None,
                False,
                cancel_token,
                3,
                2,
                False,
            )
            LOGGER.info("Mega: startDownload returned")
            LOGGER.info("Mega: wait_for_transfer starting ...")
            await async_api.wait_for_transfer()
            LOGGER.info("Mega: wait_for_transfer returned")

            if listener.is_cancelled or mega_listener.is_cancelled:
                LOGGER.info("Mega: download cancelled, returning")
                return
            if not mega_listener.retryable_error:
                LOGGER.info("Mega: download succeeded (no retryable error)")
                return
            LOGGER.warning("Mega: download attempt %d retryable: %s", attempt + 1, mega_listener.retryable_error)
            if attempt >= 4:
                await listener.on_download_error(_mega_error_format(mega_listener.retryable_error))
                return
            await _cleanup_dir(download_path)
            LOGGER.info("Mega: retry sleep %ds before attempt %d", 2 ** attempt, attempt + 2)
            await asleep(2 ** attempt)

    except Exception as e:
        LOGGER.error(f"Unexpected error in add_mega_download: {e}", exc_info=True)
        if not listener.is_cancelled:
            await listener.on_download_error(f"Internal error: {e}")
    finally:
        if async_api is not None:
            if async_api.api is not None and async_api._mega_listener is not None:
                with suppress(Exception):
                    async_api.api.removeListener(async_api._mega_listener)
            with suppress(Exception):
                await async_api.logout()
        await _release_link(listener.link)
        await _cleanup_dir(mega_base)
