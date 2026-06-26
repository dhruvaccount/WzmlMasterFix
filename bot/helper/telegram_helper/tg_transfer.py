from asyncio import Event, Lock, gather, sleep, open_connection, wait_for
from concurrent.futures import ThreadPoolExecutor
from os import cpu_count

import pyrogram
import socket
from pyrogram import Client, raw, utils
from pyrogram.connection import Connection
from pyrogram.connection.transport.tcp import TCPAbridgedO
from pyrogram.connection.transport.tcp.tcp import TCP
from pyrogram.crypto import aes
from pyrogram.errors import AuthBytesInvalid, AuthKeyDuplicated, RPCError
from pyrogram.file_id import FileType, ThumbnailSource
from pyrogram.raw.all import layer
from pyrogram.session import Auth, Session
from pyrogram.session.internals import DataCenter

from ... import LOGGER
from ...core.tg_client import TgClient

MB = 1024 * 1024

_crypto_workers = min(6, max(2, cpu_count() or 4))
pyrogram.crypto_executor = ThreadPoolExecutor(
    max_workers=_crypto_workers, thread_name_prefix="crypto"
)
Client.MAX_CONCURRENT_TRANSMISSIONS = 1000


async def _native_connect(self, address):
    host, port = address
    family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
    if self.proxy:
        import socks

        scheme = self.proxy.get("scheme")
        pt = getattr(socks, scheme.upper())
        sock = socks.socksocket(family)
        sock.set_proxy(
            proxy_type=pt, addr=self.proxy["hostname"], port=self.proxy["port"]
        )
        sock.settimeout(10)
        await self.loop.sock_connect(sock, (host, port))
        sock.setblocking(False)
        self.reader, self.writer = await open_connection(sock=sock)
    else:
        self.reader, self.writer = await wait_for(
            open_connection(host=host, port=port, family=family), 10
        )
    sock = self.writer.get_extra_info("socket")
    if sock:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * MB)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * MB)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NOTSENT_LOWAT, 64 * 1024)
        except (OSError, AttributeError):
            pass


def _native_close(self):
    if self.writer:
        self.writer.close()


_orig_tcp_init = TCP.__init__


def _tcp_init_patched(self, ipv6, proxy):
    _orig_tcp_init(self, ipv6, proxy)
    self.ipv6 = ipv6
    self.proxy = proxy


TCP.connect = _native_connect
TCP.close = _native_close
TCP.__init__ = _tcp_init_patched


async def _safe_abridged_send(self, data):
    length = len(data) // 4
    header = (
        bytes([length]) if length <= 126 else b"\x7f" + length.to_bytes(3, "little")
    )
    data = header + data
    async with self.lock:
        payload = await self.loop.run_in_executor(
            pyrogram.crypto_executor, aes.ctr256_encrypt, data, *self.encrypt
        )
        self.writer.write(payload)
        await self.writer.drain()


TCPAbridgedO.send = _safe_abridged_send

_orig_session_start = Session.start


async def _safe_session_start(self):
    if not hasattr(self, "_start_lock"):
        self._start_lock = Lock()
    async with self._start_lock:
        await _orig_session_start(self)


Session.start = _safe_session_start

_orig_session_stop = Session.stop


async def _safe_session_stop(self):
    if not hasattr(self, "_stop_lock"):
        self._stop_lock = Lock()
    async with self._stop_lock:
        await _orig_session_stop(self)


Session.stop = _safe_session_stop

_orig_dc_new = DataCenter.__new__


def _dc_media_port(cls, dc_id, test_mode, ipv6, media):
    ip, port = _orig_dc_new(cls, dc_id, test_mode, ipv6, media)
    if media and not test_mode:
        port = 5222
    return ip, port


DataCenter.__new__ = staticmethod(_dc_media_port)


class HypertgTransfer:
    def __init__(self, obj):
        self._obj = obj
        self._listener = obj._listener
        self.clients = dict(TgClient.helper_bots)
        self.work_loads = dict(TgClient.helper_loads)
        if TgClient.helper_users:
            for no, client in TgClient.helper_users.items():
                self.clients[-no] = client
            for no, load in TgClient.helper_user_loads.items():
                self.work_loads[-no] = load
        self.num_clients = len(self.clients)
        self._sessions = {}
        self._session_locks = {}
        self._cancel = Event()
        self._tasks = []
        LOGGER.info(
            f"HypertgTransfer init clients={self.num_clients} "
            f"loads={dict(self.work_loads)}"
        )

    @staticmethod
    async def create_auth(client, dc_id, tm=None):
        if tm is None:
            tm = await client.storage.test_mode()
        main_dc = await client.storage.dc_id()
        if dc_id != main_dc:
            ak = await Auth(client, dc_id, tm).create()
            return ak, True
        ak = await client.storage.auth_key()
        return ak, False

    @staticmethod
    async def start_session(s, mode=3):
        while True:
            s.connection = Connection(
                s.dc_id,
                s.test_mode,
                s.client.ipv6,
                s.client.proxy,
                s.is_media,
                mode=mode,
            )
            try:
                await s.connection.connect()
                s.network_task = s.client.loop.create_task(s.network_worker())
                await s.send(
                    raw.functions.Ping(ping_id=0), timeout=Session.START_TIMEOUT
                )
                if not s.is_cdn:
                    await s.send(
                        raw.functions.InvokeWithLayer(
                            layer=layer,
                            query=raw.functions.InitConnection(
                                api_id=await s.client.storage.api_id(),
                                app_version=s.client.app_version,
                                device_model=s.client.device_model,
                                system_version=s.client.system_version,
                                system_lang_code=s.client.lang_code,
                                lang_code=s.client.lang_code,
                                lang_pack="",
                                query=raw.functions.help.GetConfig(),
                            ),
                        ),
                        timeout=Session.START_TIMEOUT,
                    )
                s.ping_task = s.client.loop.create_task(s.ping_worker())
            except AuthKeyDuplicated as e:
                await s.stop()
                raise e
            except (OSError, TimeoutError, RPCError):
                await s.stop()
                continue
            except Exception as e:
                await s.stop()
                raise e
            else:
                break
        s.is_connected.set()

    def _get_lock(self, client_id, dc_id):
        key = (client_id, dc_id)
        if key not in self._session_locks:
            self._session_locks[key] = Lock()
        return self._session_locks[key]

    async def _mk_session(self, client, dc_id, mode=3):
        tm = await client.storage.test_mode()
        ak, is_cross = await self.create_auth(client, dc_id, tm)
        s = Session(client, dc_id, ak, tm, is_media=True)
        await self.start_session(s, mode=mode)
        if is_cross:
            for attempt in range(6):
                try:
                    e = await client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=dc_id)
                    )
                    await s.invoke(
                        raw.functions.auth.ImportAuthorization(id=e.id, bytes=e.bytes)
                    )
                    break
                except AuthBytesInvalid:
                    LOGGER.warning(
                        f"HypertgTransfer AuthBytesInvalid attempt {attempt + 1}/6 "
                        f"client={client.me.username} dc={dc_id}"
                    )
                    await sleep(1)
            else:
                await s.stop()
                LOGGER.error(f"HypertgTransfer mk_session dc={dc_id} auth failed")
                raise AuthBytesInvalid
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
                LOGGER.warning(f"HypertgTransfer warmup fail client {i}: {e}")

        await gather(*[_w(i) for i in indices])

    async def _close_all(self):
        sessions = list(self._sessions.values())
        self._sessions.clear()
        LOGGER.info(f"HypertgTransfer close_all {len(sessions)} sessions")
        for i, s in enumerate(sessions):
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
            loc = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=fid.volume_id,
                local_id=fid.local_id,
                big=fid.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
            return loc
        if ft == FileType.PHOTO:
            loc = raw.types.InputPhotoFileLocation(
                id=fid.media_id,
                access_hash=fid.access_hash,
                file_reference=fid.file_reference,
                thumb_size=fid.thumbnail_size,
            )
            return loc
        loc = raw.types.InputDocumentFileLocation(
            id=fid.media_id,
            access_hash=fid.access_hash,
            file_reference=fid.file_reference,
            thumb_size=fid.thumbnail_size,
        )
        return loc

    async def cancel(self):
        self._cancel.set()
        for t in self._tasks:
            if not t.done():
                t.cancel()
        if self._tasks:
            await gather(*self._tasks, return_exceptions=True)
        await self._close_all()
