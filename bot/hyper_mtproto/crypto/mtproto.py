import hashlib
import os
import struct

from .aes import ige256_decrypt, ige256_encrypt


def kdf(auth_key, msg_key, outgoing):
    x = 0 if outgoing else 8

    sha256_a = hashlib.sha256(msg_key + auth_key[x : x + 36]).digest()
    sha256_b = hashlib.sha256(auth_key[x + 40 : x + 76] + msg_key).digest()

    aes_key = sha256_a[:8] + sha256_b[8:24] + sha256_a[24:32]
    aes_iv = sha256_b[:8] + sha256_a[8:24] + sha256_b[24:32]

    return aes_key, aes_iv


def pack(message_data, salt, session_id, auth_key, msg_id, seq_no):
    data = salt + session_id + msg_id + seq_no
    data += struct.pack("<I", len(message_data)) + message_data
    padding = os.urandom(-(len(data) + 12) % 16 + 12)

    msg_key_large = hashlib.sha256(auth_key[88 : 88 + 32] + data + padding).digest()
    msg_key = msg_key_large[8:24]

    aes_key, aes_iv = kdf(auth_key, msg_key, outgoing=True)
    encrypted = ige256_encrypt(data + padding, aes_key, aes_iv)

    auth_key_id = hashlib.sha1(auth_key).digest()[-8:]

    return auth_key_id + msg_key + encrypted


def unpack(packet, auth_key):
    msg_key = packet[8:24]
    encrypted_data = packet[24:]

    aes_key, aes_iv = kdf(auth_key, msg_key, outgoing=False)
    decrypted = ige256_decrypt(encrypted_data, aes_key, aes_iv)

    msg_key_large = hashlib.sha256(auth_key[96 : 96 + 32] + decrypted).digest()
    msg_key_check = msg_key_large[8:24]
    if msg_key_check != msg_key:
        raise ValueError("msg_key mismatch")

    msg_id = decrypted[16:24]
    seq_no = struct.unpack("<I", decrypted[24:28])[0]
    msg_len = struct.unpack("<I", decrypted[28:32])[0]
    msg_data = decrypted[32 : 32 + msg_len]

    return msg_id, seq_no, msg_data
