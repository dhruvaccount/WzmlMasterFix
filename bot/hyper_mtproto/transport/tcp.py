import asyncio
import socket
from asyncio import Lock, open_connection, wait_for

MB = 1024 * 1024
RECV_TIMEOUT = 60


class TCP:
    def __init__(self, ipv6=False, proxy=None):
        self.ipv6 = ipv6
        self.proxy = proxy
        self.reader = None
        self.writer = None
        self.lock = Lock()
        self._closed = False

    async def connect(self, address):
        host, port = address
        family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
        if self.proxy:
            import socks

            scheme = self.proxy.get("scheme")
            pt = getattr(socks, scheme.upper())
            sock = socks.socksocket(family)
            sock.set_proxy(
                proxy_type=pt,
                addr=self.proxy["hostname"],
                port=self.proxy["port"],
            )
            sock.settimeout(10)
            loop = asyncio.get_running_loop()
            await loop.sock_connect(sock, (host, port))
            sock.setblocking(False)
            self.reader, self.writer = await open_connection(sock=sock)
        else:
            self.reader, self.writer = await wait_for(
                open_connection(host=host, port=port, family=family), 10
            )
        self._set_keepalive()
        self._closed = False

    def _set_keepalive(self):
        sock = self.writer.get_extra_info("socket")
        if sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

    async def close(self):
        if self._closed:
            return
        self._closed = True
        w = self.writer
        self.writer = None
        self.reader = None
        if w:
            try:
                w.close()
                await w.wait_closed()
            except Exception:
                pass

    async def send(self, data):
        async with self.lock:
            self.writer.write(data)
            await self.writer.drain()

    async def recv(self, length):
        return await wait_for(self.reader.readexactly(length), RECV_TIMEOUT)
