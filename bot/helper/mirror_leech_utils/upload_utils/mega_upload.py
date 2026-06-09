import os
from asyncio import TimeoutError as AsyncTimeoutError, wait_for
from contextlib import suppress
from mimetypes import guess_type
from secrets import token_hex

from aiofiles.os import makedirs, path as aiopath
from aioshutil import rmtree
from mega import MegaApi, MegaCancelToken

from .... import LOGGER, task_dict, task_dict_lock
from ...ext_utils.bot_utils import sync_to_async
from ...listeners.mega_listener import AsyncMega, MegaAppListener, _mega_error_format
from ...mirror_leech_utils.status_utils.mega_status import MegaDownloadStatus
from ...telegram_helper.message_utils import update_status_message


def _make_cancel_token():
    if MegaCancelToken is None:
        return None
    try:
        return MegaCancelToken.createInstance()
    except Exception as e:
        LOGGER.error(f"Mega: failed to create cancel token: {e}")
        return None


async def _cleanup_dir(directory: str):
    if directory and await aiopath.exists(directory):
        await rmtree(directory, ignore_errors=True)


def _find_node_by_name(api, parent_node, name):
    try:
        children = api.getChildren(parent_node)
        if children:
            for i in range(children.size()):
                child = children.get(i)
                try:
                    if child.getName() == name:
                        return child
                except Exception:
                    pass
    except Exception as e:
        LOGGER.warning(f"_find_node_by_name error: {e}")
    return None


async def _get_total_size(local_dir):
    total = 0
    walk_result = await sync_to_async(lambda: list(os.walk(local_dir)))
    for root, _, files in walk_result:
        for f in files:
            try:
                total += await aiopath.getsize(os.path.join(root, f))
            except Exception:
                pass
    return total


async def _create_mega_folder(async_api, mega_listener, name, parent_node):
    return await async_api.create_folder(name, parent_node)


async def _ensure_folder_structure(async_api, mega_listener, local_dir, parent_node, folder_name=None):
    root_node = parent_node
    if folder_name:
        root_node = await _create_mega_folder(async_api, mega_listener, folder_name, parent_node)
        if not root_node:
            LOGGER.error(f"Failed to create root folder '{folder_name}' on Mega")
            return None, {}

    folder_map = {}
    walk_result = await sync_to_async(lambda: list(os.walk(local_dir)))
    for root, dirs, _ in walk_result:
        if root == local_dir:
            parent = root_node
        else:
            parent = folder_map.get(root)
            if not parent:
                continue

        for d in dirs:
            sub_path = os.path.join(root, d)
            node = await _create_mega_folder(async_api, mega_listener, d, parent)
            if node:
                folder_map[sub_path] = node

    return root_node, folder_map


async def _upload_file(async_api, mega_listener, file_path, parent_node, custom_name, suppress_export=False):
    cancel_token = _make_cancel_token()
    mega_listener._cancel_token = cancel_token
    mega_listener.error = None
    mega_listener.retryable_error = None
    mega_listener._bytes_transferred = 0
    mega_listener._total_downloaded_bytes = 0
    mega_listener._caller_manages_completion = True
    mega_listener._size = await aiopath.getsize(file_path)

    await async_api.startUpload(
        file_path,
        parent_node,
        custom_name,
        cancel_token,
    )
    await async_api.wait_for_transfer()

    if mega_listener.is_cancelled:
        return False, None
    if mega_listener.error:
        msg = _mega_error_format(mega_listener.error)
        LOGGER.error(f"MegaUpload error: {msg}")
        return False, None

    link = None
    if not suppress_export:
        node_handle = getattr(mega_listener, "_uploaded_node_handle", None)
        if node_handle:
            try:
                await wait_for(mega_listener._export_done.wait(), timeout=60)
                link = getattr(mega_listener, "_export_link", None)
                LOGGER.info(f"MegaUpload: export result link={link}")
            except AsyncTimeoutError:
                LOGGER.warning("MegaUpload: export timed out after 60s")

    return True, link


async def add_mega_upload(listener, path, mega_email, mega_password, gid):
    if not mega_email or not mega_password:
        await listener.on_upload_error(
            "Mega credentials not configured for this user."
        )
        return

    mega_base = ""
    sdk_gid = token_hex(5)
    mega_base = os.path.join(
        os.path.dirname(path.rstrip("/")), ".mega_sdk", sdk_gid
    )
    mega_dir = os.path.join(mega_base, "main")
    await makedirs(mega_dir, exist_ok=True)
    LOGGER.info(f"DEBUG: mega_dir={mega_dir}")

    LOGGER.info(f"DEBUG: creating AsyncMega")
    async_api = AsyncMega()
    LOGGER.info(f"DEBUG: creating MegaApi")
    async_api.api = api = MegaApi("", mega_dir, "WZML-X", 4)
    LOGGER.info(f"DEBUG: MegaApi created, creating MegaAppListener")
    mega_listener = MegaAppListener(async_api, listener)
    LOGGER.info(f"DEBUG: MegaAppListener created, setting up")
    mega_listener._upload_mode = True
    async_api._mega_listener = mega_listener
    LOGGER.info(f"DEBUG: adding listener to api")
    api.addListener(mega_listener)
    LOGGER.info(f"DEBUG: listener added, entering try block")

    try:
        async with task_dict_lock:
            task_dict[listener.mid] = MegaDownloadStatus(listener, mega_listener, gid, "up")
        await update_status_message(listener.message.chat.id)

        LOGGER.info(f"DEBUG: logging in with mega_email={mega_email[:4]}...")
        await async_api.login(mega_email, mega_password)
        if mega_listener.error:
            await listener.on_upload_error(
                f"Mega login failed: {_mega_error_format(mega_listener.error)}"
            )
            return

        LOGGER.info(f"DEBUG: fetching nodes")
        await async_api.fetchNodes()
        if mega_listener.error:
            await listener.on_upload_error(
                f"Mega fetch nodes failed: {_mega_error_format(mega_listener.error)}"
            )
            return
        LOGGER.info(f"DEBUG: nodes fetched")

        root_node = mega_listener.node
        if not root_node:
            await listener.on_upload_error(
                "Failed to get Mega root node."
            )
            return
        LOGGER.info(f"DEBUG: root_node={root_node}")

        total_files = 0
        uploaded_files = 0
        mime_type = "application/octet-stream"

        upload_link = None
        is_dir = await aiopath.isdir(path)
        LOGGER.info(f"DEBUG: path_is_dir={is_dir}, path={path}")
        if is_dir:
            total_files = await sync_to_async(lambda: sum(len(files) for _, _, files in os.walk(path)))
            LOGGER.info(f"DEBUG: folder total_files={total_files}")
            if total_files == 0:
                await listener.on_upload_error("No files to upload in folder")
                return
            listener.size = await _get_total_size(path)
            dir_name = os.path.basename(path.rstrip("/\\"))
            LOGGER.info(f"DEBUG: folder dir_name={dir_name}")

            mega_root, folder_map = await _ensure_folder_structure(
                async_api, mega_listener, path, root_node, dir_name
            )
            LOGGER.info(f"DEBUG: folder_structure mega_root={mega_root}, folder_map_size={len(folder_map)}")
            if not mega_root:
                if not listener.is_cancelled:
                    await listener.on_upload_error("Failed to create root folder on Mega")
                return

            mega_listener._suppress_export = True

            walk_result = await sync_to_async(lambda: list(os.walk(path)))
            for root, _, files in walk_result:
                if listener.is_cancelled:
                    return
                if root == path:
                    parent = mega_root
                else:
                    parent = folder_map.get(root)

                if parent is None:
                    LOGGER.info(f"DEBUG: no parent for {root}, skipping")
                    continue

                for f in files:
                    if listener.is_cancelled:
                        return
                    file_path = os.path.join(root, f)
                    LOGGER.info(f"DEBUG: uploading file={f}")
                    ok, _ = await _upload_file(
                        async_api, mega_listener, file_path, parent, f, suppress_export=True
                    )
                    if ok:
                        uploaded_files += 1
                        LOGGER.info(f"DEBUG: uploaded ok={ok}, uploaded_files={uploaded_files}")
                    else:
                        if not listener.is_cancelled:
                            await listener.on_upload_error(f"MegaUpload failed for {f}")
                        return

            mime_type = "Folder"
            LOGGER.info(f"DEBUG: folder upload done, uploaded_files={uploaded_files}")
            if uploaded_files > 0 and not listener.is_cancelled:
                try:
                    mega_listener._suppress_export = False
                    LOGGER.info(f"DEBUG: exporting folder node")
                    upload_link = await async_api.export_node(mega_root)
                    LOGGER.info(f"DEBUG: folder export done, link={upload_link}")
                except Exception as e:
                    LOGGER.exception(f"MegaUpload: folder export failed: {e}")

        else:
            total_files = 1
            file_name = os.path.basename(path)
            LOGGER.info(f"DEBUG: single file, file_name={file_name}")
            listener.size = await aiopath.getsize(path)
            LOGGER.info(f"DEBUG: file size={listener.size}")
            ok, link = await _upload_file(
                async_api, mega_listener, path, root_node, file_name
            )
            LOGGER.info(f"DEBUG: upload result ok={ok}, link={link}")
            if ok:
                uploaded_files = 1
                upload_link = link
                mime_type = guess_type(file_name)[0] or "application/octet-stream"
            else:
                if not listener.is_cancelled:
                    await listener.on_upload_error(
                        f"MegaUpload failed for {file_name}"
                    )
                return

        if uploaded_files > 0 and not listener.is_cancelled:
            LOGGER.info(
                f"MegaUpload: completed, {uploaded_files}/{total_files} files"
            )
            LOGGER.info(f"DEBUG: calling on_upload_complete")
            await listener.on_upload_complete(
                upload_link, uploaded_files, 0, mime_type
            )

    except Exception as e:
        LOGGER.error(
            f"Unexpected error in add_mega_upload: {e}", exc_info=True
        )
        if not listener.is_cancelled:
            await listener.on_upload_error(f"Internal error: {e}")
    finally:
        if async_api is not None:
            with suppress(Exception):
                await async_api.logout()
        await _cleanup_dir(mega_base)
    LOGGER.info(f"DEBUG: add_mega_upload exiting")
