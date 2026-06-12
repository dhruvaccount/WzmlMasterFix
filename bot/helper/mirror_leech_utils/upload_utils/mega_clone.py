from os import path as ospath
from asyncio import sleep as asleep
from secrets import token_hex

from aiofiles.os import makedirs
from mega import MegaApi

from .... import LOGGER, task_dict, task_dict_lock
from ...telegram_helper.message_utils import update_status_message
from ...listeners.mega_listener import AsyncMega, MegaAppListener, _mega_error_format
from ...ext_utils.bot_utils import sync_to_async
from ...mirror_leech_utils.status_utils.mega_status import MegaDownloadStatus


async def _count_mega_children(api, node):
    count_files = 0
    count_folders = 0
    try:
        children = await sync_to_async(api.getChildren, node)
        if children:
            for i in range(children.size()):
                child = children.get(i)
                try:
                    if child.isFolder():
                        count_folders += 1
                        f, d = await _count_mega_children(api, child)
                        count_files += f
                        count_folders += d
                    else:
                        count_files += 1
                except Exception:
                    pass
    except Exception:
        pass
    return count_files, count_folders


async def add_mega_clone(listener, link, mega_email, mega_password, gid):
    if not mega_email or not mega_password:
        await listener.on_upload_error(
            "Mega credentials not configured for this user."
        )
        return None, 0, 0

    sdk_gid = token_hex(5)
    mega_dir = ospath.join(
        listener.message.chat.id and str(listener.message.chat.id) or "default",
        ".mega_sdk",
        sdk_gid,
        "main",
    )
    await makedirs(mega_dir, exist_ok=True)

    async_api = AsyncMega()
    async_api.api = api = MegaApi("", mega_dir, "WZML-X", 4)
    await asleep(0.1)
    mega_listener = MegaAppListener(async_api, listener)
    async_api._mega_listener = mega_listener
    api.addListener(mega_listener)
    api._listener_ref = mega_listener

    try:
        async with task_dict_lock:
            task_dict[listener.mid] = MegaDownloadStatus(listener, mega_listener, gid, "cl")
        await update_status_message(listener.message.chat.id)

        await async_api.login(mega_email, mega_password)
        if mega_listener.error:
            await listener.on_upload_error(
                f"Mega login failed: {_mega_error_format(mega_listener.error)}"
            )
            return None, 0, 0

        await async_api.fetchNodes()
        await asleep(0)
        if mega_listener.error:
            await listener.on_upload_error(
                f"Mega fetch nodes failed: {_mega_error_format(mega_listener.error)}"
            )
            return None, 0, 0

        root_node = mega_listener.node
        if not root_node:
            await listener.on_upload_error(
                "Failed to get Mega root node."
            )
            return None, 0, 0

        result = await async_api.import_link(link, root_node, auto_export=True)
        if result is None:
            if mega_listener.error:
                await listener.on_upload_error(
                    f"Mega import failed: {_mega_error_format(mega_listener.error)}"
                )
            else:
                await listener.on_upload_error("Mega import returned no node.")
            return None, 0, 0

        import_ok, export_link = result
        if not import_ok:
            await listener.on_upload_error("Mega import returned no node.")
            return None, 0, 0

        files = 1
        folders = 0
        if mega_listener._imported_node_is_folder:
            handle = mega_listener._imported_node_handle
            if handle:
                imported_folder = await sync_to_async(api.getNodeByHandle, handle)
                if imported_folder:
                    file_count, folder_count = await _count_mega_children(api, imported_folder)
                    files = file_count
                    folders = folder_count + 1
        if mega_listener._imported_node_name:
            listener.name = mega_listener._imported_node_name
        if mega_listener._imported_node_size:
            listener.size = mega_listener._imported_node_size

        return export_link or "", files, folders

    except Exception as e:
        LOGGER.error(f"MegaClone failed: {e}", exc_info=True)
        if not mega_listener.error:
            mega_listener.error = str(e)
        await listener.on_upload_error(f"Mega clone error: {e}")
        return None, 0, 0
    finally:
        try:
            await async_api.logout()
        except Exception:
            pass
        try:
            api.removeListener(mega_listener)
        except Exception:
            pass
