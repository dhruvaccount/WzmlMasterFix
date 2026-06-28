import logging

from .tcp import TCP

log = logging.getLogger(__name__)


class TCPAbridged(TCP):
    async def connect(self, address):
        log.info("TCPAbridged connect %s", address)
        await super().connect(address)
        await super().send(b"\xef")

    async def send(self, data):
        length = len(data) // 4
        if length <= 126:
            header = bytes([length])
        else:
            header = b"\x7f" + length.to_bytes(3, "little")
        async with self.lock:
            self.writer.write(header + data)
            await self.writer.drain()
        log.info("TCPAbridged sent %dB header=%s", len(data), header.hex())

    async def recv(self):
        length = await self.reader.readexactly(1)
        length = int.from_bytes(length, "little")
        if length == 0x7F:
            length = int.from_bytes(await self.reader.readexactly(3), "little")
        data = await self.reader.readexactly(length * 4)
        log.info("TCPAbridged recv %dB", len(data))
        return data
