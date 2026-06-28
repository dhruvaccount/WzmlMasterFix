import os

from ..crypto.aes import ctr256_decrypt, ctr256_encrypt
from .tcp_abridged import TCPAbridged

RESERVED = (b"HEAD", b"POST", b"GET ", b"OPTI", b"\xee" * 4)


class TCPAbridgedO(TCPAbridged):
    def __init__(self, ipv6=False, proxy=None):
        super().__init__(ipv6, proxy)
        self.enc_key = None
        self.enc_iv = None
        self.enc_state = None
        self.dec_key = None
        self.dec_iv = None
        self.dec_state = None

    async def connect(self, address):
        await TCPAbridged.connect(self, address)

        while True:
            nonce = bytearray(os.urandom(64))

            if (
                nonce[0] != 0xEF
                and nonce[:4] not in RESERVED
                and nonce[4:8] != b"\x00" * 4
            ):
                nonce[56] = nonce[57] = nonce[58] = nonce[59] = 0xEF
                break

        temp = bytearray(nonce[55:7:-1])

        self.enc_key = bytes(nonce[8:40])
        self.enc_iv = bytearray(nonce[40:56])
        self.enc_state = bytearray(1)

        self.dec_key = bytes(temp[0:32])
        self.dec_iv = bytearray(temp[32:48])
        self.dec_state = bytearray(1)

        nonce[56:64] = ctr256_encrypt(
            nonce, self.enc_key, self.enc_iv, self.enc_state
        )[56:64]

        async with self.lock:
            self.writer.write(nonce)
            await self.writer.drain()

    async def send(self, data):
        length = len(data) // 4
        if length <= 126:
            header = bytes([length])
        else:
            header = b"\x7f" + length.to_bytes(3, "little")
        payload = ctr256_encrypt(
            header + data, self.enc_key, self.enc_iv, self.enc_state
        )
        async with self.lock:
            self.writer.write(payload)
            await self.writer.drain()

    async def recv(self):
        length = await self.reader.readexactly(1)
        length = ctr256_decrypt(length, self.dec_key, self.dec_iv, self.dec_state)

        if length == b"\x7f":
            length = await self.reader.readexactly(3)
            length = ctr256_decrypt(
                length, self.dec_key, self.dec_iv, self.dec_state
            )

        data = await self.reader.readexactly(
            int.from_bytes(length, "little") * 4
        )
        return ctr256_decrypt(data, self.dec_key, self.dec_iv, self.dec_state)
