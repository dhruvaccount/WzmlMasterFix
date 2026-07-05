import os

from pyrogram import StopTransmission

from ... import LOGGER
from ...core.config_manager import Config
from ...core.tg_client import TgClient
from ..telegram_helper.tg_transfer import HypertgTransfer


class HypertgUpload(HypertgTransfer):
    def __init__(self, obj):
        super().__init__(obj)
        self._up_file = ""

    async def _progress(self, current, total, file_path):
        if self._listener.is_cancelled:
            raise StopTransmission()
        self._obj._processed_bytes = current

    async def upload(
        self,
        file_path,
        media_type,
        duration=0,
        width=0,
        height=0,
        artist="",
        title="",
        thumb_path=None,
        caption="",
        reply_to_message_id=None,
    ):
        self._cancel.clear()
        self._obj._processed_bytes = 0
        self._up_file = os.path.basename(file_path)

        idx = self._pick_client()
        client = self.clients[idx]
        self.work_loads[idx] += 1

        try:
            kwargs = {
                "chat_id": Config.LEECH_DUMP_CHAT,
                "disable_notification": True,
                "progress": self._progress,
                "progress_args": (file_path,),
            }
            if caption:
                kwargs["caption"] = caption
            if thumb_path:
                kwargs["thumb"] = thumb_path

            if media_type == "video":
                kwargs["video"] = file_path
                if duration:
                    kwargs["duration"] = duration
                if width:
                    kwargs["width"] = width
                if height:
                    kwargs["height"] = height
                sent = await client.send_video(**kwargs)
            elif media_type == "audio":
                kwargs["audio"] = file_path
                if duration:
                    kwargs["duration"] = duration
                if artist:
                    kwargs["performer"] = artist
                if title:
                    kwargs["title"] = title
                sent = await client.send_audio(**kwargs)
            elif media_type == "photo":
                kwargs["photo"] = file_path
                sent = await client.send_photo(**kwargs)
            else:
                kwargs["document"] = file_path
                sent = await client.send_document(**kwargs)

            self._obj._processed_bytes = os.path.getsize(file_path)

            if not self._listener.bot_pm:
                copied = await TgClient.bot.copy_message(
                    chat_id=self._listener.message.chat.id,
                    from_chat_id=Config.LEECH_DUMP_CHAT,
                    message_id=sent.id,
                    reply_to_message_id=reply_to_message_id,
                )
            else:
                copied = sent

            LOGGER.info(f"HypertgUL uploaded {self._up_file}")
            return copied

        except StopTransmission:
            LOGGER.warning(f"HypertgUL cancelled {self._up_file}")
            raise
        except Exception as e:
            LOGGER.error(f"HypertgUL fail {self._up_file}: {type(e).__name__}: {e}")
            raise
        finally:
            self.work_loads[idx] -= 1

    async def cancel(self):
        await super().cancel()
