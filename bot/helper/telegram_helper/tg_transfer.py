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
    LOGGER.debug(f"HypertgTCP connecting to {address}")
    await _orig_tcp_connect(self, address)
    sock = None
    if self.writer:
        try:
            sock = self.writer.get_extra_info("socket")
        except Exception as e:
            LOGGER.debug(f"HypertgTCP get socket err: {e}")
    if sock:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            LOGGER.debug(f"HypertgTCP tuned socket {address}: NODELAY=1 KEEPALIVE=1 SNDBUF=4MB RCVBUF=4MB")
        except OSError as e:
            LOGGER.debug(f"HypertgTCP socket tune failed: {e}")


TCP.connect = _tcp_tuned_connect

_orig_dc_new = DataCenter.__new__


def _dc_alt_port(cls, dc_id, test_mode, ipv6, media):
    ip, port = _orig_dc_new(cls, dc_id, test_mode, ipv6, media)
    if media and not test_mode:
        LOGGER.debug(f"HypertgDC dc={dc_id} alt port 5222 (was {port})")
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
        LOGGER.info(
            f"HypertgTransfer init clients={self.num_clients} "
            f"loads={dict(self.work_loads)}"
        )

    def _get_lock(self, client_id, dc_id):
        key = (client_id, dc_id)
        if key not in self._session_locks:
            self._session_locks[key] = Lock()
            LOGGER.debug(f"HypertgTransfer new lock client={client_id} dc={dc_id}")
        return self._session_locks[key]

    async def _mk_session(self, client, dc_id):
        tm = await client.storage.test_mode()
        main_dc = await client.storage.dc_id()
        LOGGER.info(
            f"HypertgTransfer mk_session client={client.me.username} "
            f"dc={dc_id} main_dc={main_dc} test={tm}"
        )
        if dc_id != main_dc:
            LOGGER.info(
                f"HypertgTransfer mk_session cross-dc dc={dc_id} "
                f"client={client.me.username} — creating auth"
            )
            ak = await Auth(client, dc_id, tm).create()
            s = Session(client, dc_id, ak, tm, is_media=True)
            await s.start()
            LOGGER.info(
                f"HypertgTransfer mk_session dc={dc_id} "
                f"connected={s.is_connected} — exporting auth"
            )
            for attempt in range(6):
                try:
                    e = await client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=dc_id)
                    )
                    LOGGER.info(
                        f"HypertgTransfer mk_session dc={dc_id} "
                        f"auth exported id={e.id} — importing"
                    )
                    await s.invoke(
                        raw.functions.auth.ImportAuthorization(id=e.id, bytes=e.bytes)
                    )
                    client.media_sessions[dc_id] = s
                    LOGGER.info(
                        f"HypertgTransfer mk_session dc={dc_id} "
                        f"auth imported — session ready"
                    )
                    return s
                except AuthBytesInvalid:
                    LOGGER.warning(
                        f"HypertgTransfer AuthBytesInvalid attempt {attempt + 1}/6 "
                        f"client={client.me.username} dc={dc_id}"
                    )
                    await sleep(1)
            await s.stop()
            LOGGER.error(
                f"HypertgTransfer mk_session dc={dc_id} "
                f"auth failed after 6 attempts — raising"
            )
            raise AuthBytesInvalid
        ak = await client.storage.auth_key()
        s = Session(client, dc_id, ak, tm, is_media=True)
        await s.start()
        client.media_sessions[dc_id] = s
        LOGGER.info(
            f"HypertgTransfer mk_session same-dc dc={dc_id} "
            f"client={client.me.username} connected={s.is_connected}"
        )
        return s

    async def _get_session(self, idx, dc_id, force=False):
        s = self._sessions.get(idx)
        if s and not force:
            if s.is_connected and s.dc_id == dc_id:
                LOGGER.debug(
                    f"HypertgTransfer session reuse idx={idx} "
                    f"dc={dc_id} connected={s.is_connected}"
                )
                return s
            LOGGER.info(
                f"HypertgTransfer session stale idx={idx} "
                f"old_dc={s.dc_id} new_dc={dc_id} connected={s.is_connected} — stopping"
            )
            try:
                await s.stop()
            except Exception as e:
                LOGGER.debug(f"HypertgTransfer session stop err: {e}")
        lock = self._get_lock(id(self.clients[idx]), dc_id)
        LOGGER.debug(f"HypertgTransfer session acquire lock idx={idx} dc={dc_id}")
        async with lock:
            s = self._sessions.get(idx)
            if s and not force:
                if s.is_connected and s.dc_id == dc_id:
                    LOGGER.debug(
                        f"HypertgTransfer session reuse (double-check) idx={idx} dc={dc_id}"
                    )
                    return s
            LOGGER.info(
                f"HypertgTransfer session creating idx={idx} "
                f"dc={dc_id} client={self.clients[idx].me.username}"
            )
            s = await self._mk_session(self.clients[idx], dc_id)
            self._sessions[idx] = s
            LOGGER.info(
                f"HypertgTransfer session created idx={idx} "
                f"dc={dc_id} connected={s.is_connected}"
            )
        return s

    async def _warmup(self, indices, dc_id):
        LOGGER.info(f"HypertgTransfer warmup indices={list(indices)} dc={dc_id}")

        async def _w(i):
            try:
                s = await self._get_session(i, dc_id)
                LOGGER.info(
                    f"HypertgTransfer warmup ok client={i} "
                    f"dc={dc_id} connected={s.is_connected}"
                )
            except Exception as e:
                LOGGER.warning(f"HypertgTransfer warmup fail client {i}: {e}")

        await gather(*[_w(i) for i in indices])
        LOGGER.info(f"HypertgTransfer warmup done indices={list(indices)}")

    async def _close_all(self):
        sessions = list(self._sessions.values())
        self._sessions.clear()
        LOGGER.info(f"HypertgTransfer close_all {len(sessions)} sessions")
        for i, s in enumerate(sessions):
            try:
                for client in self.clients.values():
                    if s in client.media_sessions.values():
                        LOGGER.debug(
                            f"HypertgTransfer close_all session {i} "
                            f"dc={s.dc_id} in client media_sessions — skipping"
                        )
                        break
                else:
                    if s.is_connected:
                        await s.stop()
                        LOGGER.info(f"HypertgTransfer close_all session {i} dc={s.dc_id} stopped")
                    else:
                        LOGGER.debug(f"HypertgTransfer close_all session {i} dc={s.dc_id} already disconnected")
            except Exception as e:
                LOGGER.warning(f"HypertgTransfer close_all session {i} stop err: {e}")

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
            loc = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=fid.volume_id,
                local_id=fid.local_id,
                big=fid.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
            LOGGER.debug(f"HypertgTransfer location CHAT_PHOTO vol={fid.volume_id} local={fid.local_id}")
            return loc
        if ft == FileType.PHOTO:
            loc = raw.types.InputPhotoFileLocation(
                id=fid.media_id,
                access_hash=fid.access_hash,
                file_reference=fid.file_reference,
                thumb_size=fid.thumbnail_size,
            )
            LOGGER.debug(f"HypertgTransfer location PHOTO id={fid.media_id}")
            return loc
        loc = raw.types.InputDocumentFileLocation(
            id=fid.media_id,
            access_hash=fid.access_hash,
            file_reference=fid.file_reference,
            thumb_size=fid.thumbnail_size,
        )
        LOGGER.debug(f"HypertgTransfer location DOCUMENT id={fid.media_id}")
        return loc

    async def cancel(self):
        LOGGER.info("HypertgTransfer cancel called")
        self._cancel.set()
        for t in self._tasks:
            if not t.done():
                t.cancel()
        if self._tasks:
            await gather(*self._tasks, return_exceptions=True)
        await self._close_all()
        LOGGER.info("HypertgTransfer cancel done")
