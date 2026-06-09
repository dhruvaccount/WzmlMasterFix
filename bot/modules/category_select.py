from time import time

from .. import bot_cache, categories_dict, task_dict, task_dict_lock
from ..helper.ext_utils.bot_utils import (
    MirrorStatus,
    arg_parser,
    fetch_drive_cat,
    get_readable_time,
    is_gdrive_link,
    new_task,
    sync_to_async,
)
from ..helper.ext_utils.status_utils import get_task_by_gid
from ..helper.mirror_leech_utils.gdrive_utils.helper import GoogleDriveHelper
from pyrogram.enums import ButtonStyle
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.filters import CustomFilters
from ..helper.telegram_helper.message_utils import (
    edit_message,
    open_category_btns,
    send_message,
)


async def change_category(client, message):
    if not message.from_user:
        return
    user_id = message.from_user.id

    text = message.text.split("\n")
    input_list = text[0].split(" ")

    arg_base = {"link": "", "-id": "", "-index": ""}
    args = arg_parser(input_list[1:], arg_base)

    drive_id = args["-id"]
    index_link = args["-index"]

    if drive_id and is_gdrive_link(drive_id):
        drive_id = GoogleDriveHelper.getIdFromUrl(drive_id)

    dl = None
    if gid := args["link"]:
        dl = await get_task_by_gid(gid)
        if not dl:
            await send_message(message, f"GID: <code>{gid}</code> Not Found.")
            return
    if reply_to := message.reply_to_message:
        async with task_dict_lock:
            dl = task_dict.get(reply_to.id, None)
        if not dl:
            await send_message(message, "This is not an active task!")
            return
    if not dl:
        await send_message(message, "Provide a task GID or reply to an active task.")
        return
    if (
        not await CustomFilters.sudo("", message)
        and dl.listener.message.from_user.id != user_id
    ):
        await send_message(message, "This task is not for you!")
        return
    if dl.status() not in [
        MirrorStatus.STATUS_DOWNLOAD,
        MirrorStatus.STATUS_PAUSED,
        MirrorStatus.STATUS_QUEUEDL,
    ]:
        await send_message(
            message,
            f"Task should be on {MirrorStatus.STATUS_DOWNLOAD} or "
            f"{MirrorStatus.STATUS_PAUSED} or {MirrorStatus.STATUS_QUEUEDL}",
        )
        return
    listener = dl.listener if hasattr(dl, "listener") else None
    if listener and not listener.is_leech:
        if not index_link and not drive_id:
            drive_id, index_link, is_cancelled = await open_category_btns(message)
        if is_cancelled:
            return
        if not index_link and not drive_id:
            return await send_message(message, "Time out")
        msg = "<b>Task has been Updated Successfully!</b>"
        if drive_id:
            if not (
                folder_name := await sync_to_async(
                    GoogleDriveHelper().getFolderData, drive_id
                )
            ):
                return await send_message(
                    message, "Google Drive id validation failed!!"
                )
            if listener.drive_id and listener.drive_id == drive_id:
                msg += (
                    f"\n\n<b>Folder name</b> : {folder_name} Already selected"
                )
            else:
                msg += f"\n\n<b>Folder name</b> : {folder_name}"
            listener.drive_id = drive_id
        if index_link:
            listener.index_link = index_link
            msg += f"\n\n<b>Index Link</b> : <code>{index_link}</code>"
        return await send_message(message, msg)
    else:
        await send_message(message, "Can not change Category for this task!")


@new_task
async def confirm_category(client, query):
    user_id = query.from_user.id
    data = query.data.split(maxsplit=3)
    msg_id = int(data[2])
    if msg_id not in bot_cache:
        return await edit_message(query.message, "<b>Old Task</b>")
    elif user_id != int(data[1]) and not await CustomFilters.sudo("", query):
        return await query.answer(text="This task is not for you!", show_alert=True)
    elif data[3] == "sdone":
        bot_cache[msg_id][2] = True
        return
    elif data[3] == "scancel":
        bot_cache[msg_id][3] = True
        return
    await query.answer()
    dcats = fetch_drive_cat(user_id)
    merged_dict = {**dcats, **categories_dict}
    cat_name = data[3].replace("_", " ")
    bot_cache[msg_id][0] = merged_dict[cat_name].get("drive_id")
    bot_cache[msg_id][1] = merged_dict[cat_name].get("index_link")
    buttons = ButtonMaker()
    for _name in merged_dict:
        buttons.data_button(
            f'{"✓️" if cat_name == _name else ""} {_name}',
            f"scat {user_id} {msg_id} {_name.replace(' ', '_')}",
        )
    buttons.data_button(
        "Cancel", f"scat {user_id} {msg_id} scancel", "footer", style=ButtonStyle.DANGER
    )
    buttons.data_button(
        f"Done ({get_readable_time(60 - (time() - bot_cache[msg_id][4]))})",
        f"scat {user_id} {msg_id} sdone",
        "footer",
        style=ButtonStyle.SUCCESS,
    )
    await edit_message(
        query.message,
        f"<b>Select the category where you want to upload</b>\n\n"
        f"<i><b>Upload Category:</b></i> <code>{cat_name}</code>\n\n"
        f"<b>Timeout:</b> 60 sec",
        buttons.build_menu(3),
    )


