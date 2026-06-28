import asyncio
import os
from asyncio import Event, Lock, wait_for as async_wait
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from pyrogram import raw
from pyrogram.errors import FloodWait
from pyrogram.raw.all import layer
from pyrogram.raw.core import TLObject

from .connection import Connection
from .crypto import mtproto as mtproto_crypto
from .msg_id import generate_msg_id
from .seq_no import SeqNo

START_TIMEOUT = 30


class SaltRetry(Exception):
    def __init__(self, new_salt):
        self.new_salt = new_salt


class Session:
    def __init__(
        self, client, dc_id, auth_key, test_mode, is_media=False, is_cdn=False
    ):
        self.client = client
        self.dc_id = dc_id
        self.auth_key = auth_key
        self.test_mode = test_mode
        self.is_media = is_media
        self.is_cdn = is_cdn
        self.connection = None
        self.session_id = os.urandom(8)
        self.server_salt = None
        self.seq_no = SeqNo()
        self._pending = {}
        self._invoke_lock = Lock()
        self._closed = False
        self.is_connected = Event()
        self.network_task = None
        self.ping_task = None
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"hmtp-{dc_id}"
        )

    async def start(self, mode=3):
        self.connection = Connection(
            self.dc_id,
            self.test_mode,
            self.client.ipv6,
            self.client.proxy,
            self.is_media,
            mode=mode,
        )
        await self.connection.connect()

        self.network_task = asyncio.create_task(self._network_worker())

        await self.invoke(raw.functions.Ping(ping_id=0), timeout=START_TIMEOUT)

        if not self.is_cdn:
            api_id = await self.client.storage.api_id()
            cl = self.client
            init = raw.functions.InvokeWithLayer(
                layer=layer,
                query=raw.functions.InitConnection(
                    api_id=api_id,
                    app_version=cl.app_version,
                    device_model=cl.device_model,
                    system_version=cl.system_version,
                    system_lang_code=cl.lang_code,
                    lang_code=cl.lang_code,
                    lang_pack="",
                    query=raw.functions.help.GetConfig(),
                ),
            )
            await self.invoke(init, timeout=START_TIMEOUT)

        self.ping_task = asyncio.create_task(self._ping_worker())
        self.is_connected.set()

    async def stop(self):
        self._closed = True
        if self.ping_task:
            self.ping_task.cancel()
            try:
                await self.ping_task
            except Exception:
                pass
            self.ping_task = None
        if self.network_task:
            self.network_task.cancel()
            try:
                await self.network_task
            except Exception:
                pass
            self.network_task = None
        if self.connection:
            try:
                await self.connection.close()
            except Exception:
                pass
            self.connection = None
        self._executor.shutdown(wait=False)

    async def invoke(self, query, timeout=None, retries=0, sleep_threshold=0):
        async with self._invoke_lock:
            return await self._invoke(
                query, timeout=timeout, retries=retries, sleep_threshold=sleep_threshold
            )

    async def _invoke(self, query, timeout=None, retries=0, sleep_threshold=0):
        loop = asyncio.get_running_loop()
        msg_id = generate_msg_id()

        salt = self.server_salt if self.server_salt is not None else b"\x00" * 8
        seq_no = self.seq_no(is_content=True)

        query_bytes = await loop.run_in_executor(self._executor, query.write)

        payload = await loop.run_in_executor(
            self._executor,
            mtproto_crypto.pack,
            query_bytes,
            salt,
            self.session_id,
            self.auth_key,
            msg_id,
            seq_no,
        )

        future = loop.create_future()
        int_msg_id = int.from_bytes(msg_id, "little", signed=True)
        self._pending[int_msg_id] = (future, seq_no)

        try:
            await self.connection.send(payload)
        except Exception:
            self._pending.pop(int_msg_id, None)
            raise

        try:
            return await async_wait(future, timeout=timeout)
        except SaltRetry as e:
            self.server_salt = e.new_salt
            return await self._invoke(
                query, timeout=timeout, sleep_threshold=sleep_threshold
            )
        except FloodWait as e:
            if e.value <= sleep_threshold:
                await asyncio.sleep(e.value)
                return await self._invoke(
                    query, timeout=timeout, sleep_threshold=sleep_threshold
                )
            raise
        except asyncio.TimeoutError:
            self._pending.pop(int_msg_id, None)
            raise

    async def _network_worker(self):
        while not self._closed:
            try:
                data = await self.connection.recv()
                (
                    msg_id,
                    seq_no,
                    msg_data,
                ) = await asyncio.get_running_loop().run_in_executor(
                    self._executor, mtproto_crypto.unpack, data, self.auth_key
                )

                result = await asyncio.get_running_loop().run_in_executor(
                    self._executor, TLObject.read, BytesIO(msg_data)
                )

                # Server-initiated: new session salt
                if isinstance(result, raw.types.NewSessionCreated):
                    self.server_salt = result.server_salt
                    continue

                # Server-initiated: bad server salt — update and retry
                if isinstance(result, raw.types.BadServerSalt):
                    self.server_salt = result.new_server_salt
                    future, _ = self._pending.pop(result.bad_msg_id, (None, None))
                    if future and not future.done():
                        future.set_exception(SaltRetry(result.new_server_salt))
                    continue

                # Server-initiated: bad msg notification (error 48 = bad salt)
                if isinstance(result, raw.types.BadMsgNotification):
                    if result.error_code == 48:
                        future, _ = self._pending.pop(result.bad_msg_id, (None, None))
                        if future and not future.done():
                            new_salt = self.server_salt or b"\x00" * 8
                            future.set_exception(SaltRetry(new_salt))
                    continue

                # Server-initiated: ack — silently ignore
                if isinstance(result, raw.types.MsgsAck):
                    continue

                # RPC result: match by req_msg_id, unwrap inner result
                if isinstance(result, raw.types.RpcResult):
                    future, _ = self._pending.pop(
                        result.req_msg_id, (None, None)
                    )
                    if future is None or future.done():
                        continue
                    inner = result.result
                    if isinstance(inner, raw.types.RpcError):
                        from pyrogram.errors import RPCError as RPCErrorCls

                        try:
                            RPCErrorCls.raise_it(inner)
                        except Exception as exc:
                            future.set_exception(exc)
                    else:
                        future.set_result(inner)
                    continue

                # Fallback: match by transport msg_id (Pong, etc.)
                int_msg_id = int.from_bytes(msg_id, "little", signed=True)
                future, _ = self._pending.pop(int_msg_id, (None, None))
                if future and not future.done():
                    if isinstance(result, raw.types.RpcError):
                        from pyrogram.errors import RPCError as RPCErrorCls

                        try:
                            RPCErrorCls.raise_it(result)
                        except Exception as exc:
                            future.set_exception(exc)
                    else:
                        future.set_result(result)
            except asyncio.CancelledError:
                break
            except Exception:
                if not self._closed:
                    self._closed = True
                raise

    async def _ping_worker(self):
        while not self._closed:
            await asyncio.sleep(60)
            try:
                await self.invoke(raw.functions.Ping(ping_id=0), timeout=30)
            except Exception:
                pass
