import socket
from asyncio import Lock, Event, gather, sleep
from concurrent.futures import ThreadPoolExecutor
from os import cpu_count

import pyrogram
from pyrogram import raw, utils
from pyrogram.connection.transport.tcp.tcp import TCP
from pyrogram.errors import AuthBytesInvalid
from pyrogram.file_id import FileType, ThumbnailSource
from pyrogram.session import Auth, Session
from pyrogram.session.internals import DataCenter

from ... import LOGGER
from ...core.tg_client import TgClient

pyrogram.crypto_executor = ThreadPoolExecutor(
    max_workers=min(16, (cpu_count() or 4) * 2), thread_name_prefix="crypto"
)

_orig_tcp_connect = TCP.connect


async def _tcp_tuned_connect(self, address):
    await _orig_tcp_connect(self, address)
    sock = None
    if self.writer:
        try:
            sock = self.writer.get_extra_info("socket")
        except Exception:
            pass
    if sock:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except OSError:
            pass


TCP.connect = _tcp_tuned_connect

_orig_dc_new = DataCenter.__new__


def _dc_alt_port(cls, dc_id, test_mode, ipv6, media):
    ip, port = _orig_dc_new(cls, dc_id, test_mode, ipv6, media)
    if media and not test_mode:
        port = 5222
    return ip, port


DataCenter.__new__ = staticmethod(_dc_alt_port)

MB = 1024 * 1024


class HypertgTransfer:
    def __init__(self, obj):
        self._obj = obj
        self._listener = obj._listener
        self.clients = TgClient.helper_bots
        self.work_loads = TgClient.helper_loads
        self.num_clients = len(self.clients)
        self._sessions = {}
        self._session_locks = {}
        self._cancel = Event()
        self._tasks = []

    def _get_lock(self, client_id, dc_id):
        key = (client_id, dc_id)
        if key not in self._session_locks:
            self._session_locks[key] = Lock()
        return self._session_locks[key]

    async def _mk_session(self, client, dc_id):
        tm = await client.storage.test_mode()
        if dc_id != await client.storage.dc_id():
            ak = await Auth(client, dc_id, tm).create()
            s = Session(client, dc_id, ak, tm, is_media=True)
            await s.start()
            for attempt in range(6):
                try:
                    e = await client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=dc_id)
                    )
                    await s.invoke(
                        raw.functions.auth.ImportAuthorization(id=e.id, bytes=e.bytes)
                    )
                    client.media_sessions[dc_id] = s
                    return s
                except AuthBytesInvalid:
                    LOGGER.warning(
                        f"Hypertg AuthBytesInvalid attempt {attempt + 1}/6 "
                        f"client={client.me.username} dc={dc_id}"
                    )
                    await sleep(1)
            await s.stop()
            raise AuthBytesInvalid
        ak = await client.storage.auth_key()
        s = Session(client, dc_id, ak, tm, is_media=True)
        await s.start()
        client.media_sessions[dc_id] = s
        return s

    async def _get_session(self, idx, dc_id, force=False):
        s = self._sessions.get(idx)
        if s and not force:
            if s.is_connected and s.dc_id == dc_id:
                return s
            try:
                await s.stop()
            except Exception:
                pass
        lock = self._get_lock(id(self.clients[idx]), dc_id)
        async with lock:
            s = self._sessions.get(idx)
            if s and not force:
                if s.is_connected and s.dc_id == dc_id:
                    return s
            s = await self._mk_session(self.clients[idx], dc_id)
            self._sessions[idx] = s
        return s

    async def _warmup(self, indices, dc_id):
        async def _w(i):
            try:
                await self._get_session(i, dc_id)
            except Exception as e:
                LOGGER.warning(f"Hypertg warmup fail client {i}: {e}")

        await gather(*[_w(i) for i in indices])

    async def _close_all(self):
        sessions = list(self._sessions.values())
        self._sessions.clear()
        for s in sessions:
            try:
                for client in self.clients.values():
                    if s in client.media_sessions.values():
                        break
                else:
                    if s.is_connected:
                        await s.stop()
            except Exception:
                pass

    @staticmethod
    def _location(fid):
        ft = fid.file_type
        if ft == FileType.CHAT_PHOTO:
            if fid.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=fid.chat_id, access_hash=fid.chat_access_hash
                )
            elif fid.chat_access_hash == 0:
                peer = raw.types.InputPeerChat(chat_id=-fid.chat_id)
            else:
                peer = raw.types.InputPeerChannel(
                    channel_id=utils.get_channel_id(fid.chat_id),
                    access_hash=fid.chat_access_hash,
                )
            return raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=fid.volume_id,
                local_id=fid.local_id,
                big=fid.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        if ft == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=fid.media_id,
                access_hash=fid.access_hash,
                file_reference=fid.file_reference,
                thumb_size=fid.thumbnail_size,
            )
        return raw.types.InputDocumentFileLocation(
            id=fid.media_id,
            access_hash=fid.access_hash,
            file_reference=fid.file_reference,
            thumb_size=fid.thumbnail_size,
        )

    async def cancel(self):
        self._cancel.set()
        for t in self._tasks:
            if not t.done():
                t.cancel()
        if self._tasks:
            await gather(*self._tasks, return_exceptions=True)
        await self._close_all()
