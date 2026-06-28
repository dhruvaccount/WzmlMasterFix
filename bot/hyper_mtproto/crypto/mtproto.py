import hashlib
import struct

from .aes import ige_decrypt, ige_encrypt


def _calc_key(auth_key, msg_key, is_client):
    x = 0 if is_client else 8

    sha1_a = hashlib.sha1(msg_key + auth_key[x : x + 32]).digest()
    sha1_b = hashlib.sha1(
        auth_key[x + 32 : x + 48] + msg_key + auth_key[x + 48 : x + 64]
    ).digest()
    sha1_c = hashlib.sha1(auth_key[x + 64 : x + 96] + msg_key).digest()
    sha1_d = hashlib.sha1(msg_key + auth_key[x + 96 : x + 128]).digest()

    key = sha1_a[:8] + sha1_b[8:20] + sha1_c[4:16]
    iv = sha1_a[8:20] + sha1_b[:8] + sha1_c[16:20] + sha1_d[:4]

    return key, iv


def pack(message_data, salt, session_id, auth_key, msg_id, seq_no):
    data = salt + session_id + msg_id + struct.pack("<I", seq_no)
    data += struct.pack("<I", len(message_data)) + message_data
    data += bytes(-len(data) % 16)

    msg_key = hashlib.sha1(data).digest()[4:20]

    aes_key, aes_iv = _calc_key(auth_key, msg_key, is_client=True)
    encrypted = ige_encrypt(data, aes_key, aes_iv)

    auth_key_id = hashlib.sha1(auth_key).digest()[-8:]

    return auth_key_id + msg_key + encrypted


def unpack(packet, auth_key):
    msg_key = packet[8:24]
    encrypted_data = packet[24:]

    aes_key, aes_iv = _calc_key(auth_key, msg_key, is_client=False)
    decrypted = ige_decrypt(encrypted_data, aes_key, aes_iv)

    msg_key_check = hashlib.sha1(decrypted).digest()[4:20]
    if msg_key_check != msg_key:
        raise ValueError("msg_key mismatch")

    msg_id = decrypted[16:24]
    seq_no = struct.unpack("<I", decrypted[24:28])[0]
    msg_len = struct.unpack("<I", decrypted[28:32])[0]
    msg_data = decrypted[32 : 32 + msg_len]

    return msg_id, seq_no, msg_data
