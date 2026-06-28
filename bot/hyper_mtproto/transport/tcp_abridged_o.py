import hashlib
import os
import struct

from ..crypto.aes import ctr256_encrypt as ctr_enc, ige_decrypt, ige_encrypt
from .tcp_abridged import TCPAbridged


class TCPAbridgedO(TCPAbridged):
    def __init__(self, ipv6=False, proxy=None):
        super().__init__(ipv6, proxy)
        self.enc_key = None
        self.enc_iv = None
        self.dec_key = None
        self.dec_iv = None

    async def connect(self, address):
        await TCPAbridged.connect(self, address)
        temp = bytearray(os.urandom(64))
        temp[0] = 0xEF
        temp[56:60] = temp[60:64][::-1]

        temp_key = hashlib.sha256(temp[8:40]).digest()
        temp_iv = hashlib.sha256(temp[40:56] + temp[0:8]).digest()[:16]
        encrypted = ige_encrypt(bytes(temp[:56]), temp_key, temp_iv)
        header = encrypted + bytes(temp[56:64])

        self.writer.write(header)
        await self.writer.drain()

        response = bytearray(await self.reader.readexactly(64))

        self.enc_key = bytes(temp[8:40])
        self.enc_iv = bytearray(temp[40:56])
        server_decrypted = ige_decrypt(bytes(response[:56]), temp_key, temp_iv)
        self.dec_key = server_decrypted[8:40]
        self.dec_iv = bytearray(server_decrypted[40:56])

    async def send(self, data):
        length = len(data) // 4
        if length <= 126:
            header = bytes([length])
        else:
            header = b"\x7f" + length.to_bytes(3, "little")
        payload = ctr_enc(header + data, self.enc_key, self.enc_iv)
        async with self.lock:
            self.writer.write(payload)
            await self.writer.drain()

    async def recv(self):
        encrypted_len = await self.reader.readexactly(4)
        decrypted_len = ctr_enc(encrypted_len, self.dec_key, self.dec_iv)
        length = decrypted_len[0]
        if length == 0x7F:
            length = struct.unpack("<I", decrypted_len[1:4] + b"\x00")[0]
        data_length = length * 4
        encrypted_data = await self.reader.readexactly(data_length)
        return ctr_enc(encrypted_data, self.dec_key, self.dec_iv)
