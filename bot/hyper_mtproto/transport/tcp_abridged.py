
from .tcp import TCP


class TCPAbridged(TCP):
    async def connect(self, address):
        await super().connect(address)
        self.writer.write(b"\xef\xef\xef\xef")
        await self.writer.drain()
        await self.reader.readexactly(4)

    async def send(self, data):
        length = len(data) // 4
        if length <= 126:
            header = bytes([length])
        else:
            header = b"\x7f" + length.to_bytes(3, "little")
        async with self.lock:
            self.writer.write(header + data)
            await self.writer.drain()

    async def recv(self):
        length = await self.reader.readexactly(1)
        length = int.from_bytes(length, "little")
        if length == 0x7F:
            length = int.from_bytes(await self.reader.readexactly(3), "little")
        return await self.reader.readexactly(length * 4)
