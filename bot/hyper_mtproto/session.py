import asyncio
import logging
import os
from asyncio import Event, Lock, wait_for as async_wait
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from pyrogram import raw
from pyrogram.raw.all import layer
from pyrogram.raw.core import Message, MsgContainer, FutureSalts

from .connection import Connection
from .crypto import mtproto as mtproto_crypto
from .msg_id import generate_msg_id
from .seq_no import SeqNo

log = logging.getLogger(__name__)

START_TIMEOUT = 30


class SaltRetry(Exception):
    def __init__(self, new_salt):
        self.new_salt = new_salt


class Result:
    def __init__(self):
        self.value = None
        self.event = asyncio.Event()


class Session:
    TRANSPORT_ERRORS = {
        404: "auth key not found",
        429: "transport flood",
        444: "invalid DC",
    }

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
        self.salt = 0
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
        try:
            self.connection = Connection(
                self.dc_id,
                self.test_mode,
                self.client.ipv6,
                self.client.proxy,
                self.is_media,
                mode=mode,
            )
            await self.connection.connect()
            log.info("Session DC%d connected (mode=%d)", self.dc_id, mode)

            self.network_task = asyncio.create_task(self._network_worker())

            log.info("Session DC%d sending Ping...", self.dc_id)
            await self.invoke(raw.functions.Ping(ping_id=0), timeout=START_TIMEOUT)
            log.info("Session DC%d Ping OK", self.dc_id)

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
            log.info("Session DC%d started", self.dc_id)
        except Exception:
            log.warning(
                "Session DC%d start failed, stopping", self.dc_id, exc_info=True
            )
            await self.stop()
            raise

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
        seq_no = self.seq_no(is_content=True)

        # Build message bytes: salt + session_id + msg_id + seq_no + length + body
        salt_bytes = self.salt.to_bytes(8, "little", signed=True)
        # msg_id already packed by generate_msg_id as bytes
        query_bytes = await loop.run_in_executor(self._executor, query.write)
        payload = await loop.run_in_executor(
            self._executor,
            mtproto_crypto.pack,
            query_bytes,
            salt_bytes,
            self.session_id,
            self.auth_key,
            msg_id,
            seq_no,
        )

        int_msg_id = int.from_bytes(msg_id, "little", signed=True)
        qname = (
            query.QUALNAME.rsplit(".", 1)[-1]
            if hasattr(query, "QUALNAME")
            else type(query).__name__
        )

        self._pending[int_msg_id] = Result()

        try:
            await self.connection.send(payload)
            log.info(
                "Session DC%d sent %s msg_id=%d payload=%dB",
                self.dc_id,
                qname,
                int_msg_id,
                len(payload),
            )
        except Exception:
            self._pending.pop(int_msg_id, None)
            log.warning("Session DC%d send %s failed", self.dc_id, qname, exc_info=True)
            raise

        try:
            result = await async_wait(
                self._pending[int_msg_id].event.wait(), timeout=timeout
            )
        except asyncio.TimeoutError:
            log.warning(
                "Session DC%d %s timeout msg_id=%d pending=%s",
                self.dc_id,
                qname,
                int_msg_id,
                {k: type(v).__name__ for k, v in self._pending.items()},
            )
            self._pending.pop(int_msg_id, None)
            raise

        result = self._pending.pop(int_msg_id).value

        if isinstance(result, raw.types.BadServerSalt):
            self.salt = result.new_server_salt
            log.info(
                "Session DC%d %s BadServerSalt -> new_salt=%d retry",
                self.dc_id,
                qname,
                self.salt,
            )
            return await self._invoke(
                query, timeout=timeout, sleep_threshold=sleep_threshold
            )

        if isinstance(result, raw.types.BadMsgNotification):
            if result.error_code == 48:
                log.info(
                    "Session DC%d %s BadMsgNotification code=48 salt retry",
                    self.dc_id,
                    qname,
                )
                return await self._invoke(
                    query, timeout=timeout, sleep_threshold=sleep_threshold
                )
            log.warning(
                "Session DC%d %s BadMsgNotification code=%d",
                self.dc_id,
                qname,
                result.error_code,
            )

        if isinstance(result, raw.types.RpcError):
            from pyrogram.errors import RPCError as RPCErrorCls

            RPCErrorCls.raise_it(result)

        log.info(
            "Session DC%d %s OK result=%s", self.dc_id, qname, type(result).__name__
        )
        return result

    async def handle_packet(self, data):
        loop = asyncio.get_running_loop()
        try:
            _, _, plain_text = await loop.run_in_executor(
                self._executor, mtproto_crypto.unpack, data, self.auth_key
            )
        except ValueError as e:
            log.warning("Session DC%d unpack failed: %s", self.dc_id, e)
            return

        message = await loop.run_in_executor(
            self._executor, Message.read, BytesIO(plain_text[16:])
        )

        rtype = type(message.body).__name__
        log.info("Session DC%d recv: %s", self.dc_id, rtype)

        messages = (
            message.body.messages
            if isinstance(message.body, MsgContainer)
            else [message]
        )

        for msg in messages:
            if isinstance(msg.body, raw.types.MsgsAck):
                continue

            if isinstance(msg.body, raw.types.NewSessionCreated):
                self.salt = msg.body.server_salt
                log.info(
                    "Session DC%d NewSessionCreated salt=%d", self.dc_id, self.salt
                )
                continue

            if isinstance(
                msg.body, (raw.types.MsgDetailedInfo, raw.types.MsgNewDetailedInfo)
            ):
                continue

            match_id = None

            if isinstance(
                msg.body, (raw.types.BadMsgNotification, raw.types.BadServerSalt)
            ):
                match_id = msg.body.bad_msg_id
            elif isinstance(msg.body, (raw.types.RpcResult, FutureSalts)):
                match_id = msg.body.req_msg_id
            elif isinstance(msg.body, raw.types.Pong):
                match_id = msg.body.msg_id
            else:
                log.info(
                    "Session DC%d unhandled body type=%s",
                    self.dc_id,
                    type(msg.body).__name__,
                )

            if match_id is not None and match_id in self._pending:
                self._pending[match_id].value = getattr(msg.body, "result", msg.body)
                self._pending[match_id].event.set()
            elif match_id is not None:
                log.info(
                    "Session DC%d unmatched response msg_id=%d type=%s",
                    self.dc_id,
                    match_id,
                    type(msg.body).__name__,
                )

    async def _network_worker(self):
        log.info("Session DC%d NetworkTask started", self.dc_id)
        while not self._closed:
            try:
                packet = await self.connection.recv()
                transport_code = packet[:4]
                if len(packet) == 4:
                    code = int.from_bytes(transport_code, "little", signed=True)
                    err = self.TRANSPORT_ERRORS.get(code, f"unknown error {code}")
                    log.warning("Session DC%d transport error: %s", self.dc_id, err)
                    if self.is_connected.is_set():
                        break
                    continue

                await self.handle_packet(packet)
            except asyncio.CancelledError:
                break
            except Exception:
                if not self._closed:
                    self._closed = True
                log.warning(
                    "Session DC%d network_worker error", self.dc_id, exc_info=True
                )
                raise

    async def _ping_worker(self):
        while not self._closed:
            await asyncio.sleep(60)
            try:
                await self.invoke(raw.functions.Ping(ping_id=0), timeout=30)
            except Exception:
                pass
