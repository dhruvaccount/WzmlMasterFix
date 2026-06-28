import logging

from .data_center import get_dc_address
from .transport.tcp_abridged import TCPAbridged
from .transport.tcp_abridged_o import TCPAbridgedO

log = logging.getLogger(__name__)


class Connection:
    def __init__(self, dc_id, test_mode, ipv6, proxy, is_media, mode=3):
        self.dc_id = dc_id
        self.test_mode = test_mode
        self.ipv6 = ipv6
        self.proxy = proxy
        self.is_media = is_media
        self.mode = mode
        self.transport = None

    async def connect(self):
        host, port = get_dc_address(self.dc_id, self.test_mode, media=self.is_media)

        tmode = "TCPAbridgedO" if self.mode == 3 else "TCPAbridged"
        log.info("Connecting DC%d %s:%d transport=%s", self.dc_id, host, port, tmode)

        if self.mode == 3:
            self.transport = TCPAbridgedO(ipv6=self.ipv6, proxy=self.proxy)
        else:
            self.transport = TCPAbridged(ipv6=self.ipv6, proxy=self.proxy)

        await self.transport.connect((host, port))

    async def send(self, data):
        await self.transport.send(data)

    async def recv(self):
        return await self.transport.recv()

    async def close(self):
        if self.transport:
            await self.transport.close()
