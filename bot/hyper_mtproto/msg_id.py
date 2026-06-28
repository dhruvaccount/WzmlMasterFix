import time
from struct import pack


last_msg_id = 0


def generate_msg_id():
    global last_msg_id
    now = time.time()
    nanoseconds = int((now - int(now)) * 1_000_000_000)
    seconds = int(now)
    msg_id = (seconds << 32) | (nanoseconds & 0xFFFFFFFF)
    if msg_id % 4 != 0:
        msg_id += 4 - (msg_id % 4)
    if msg_id <= last_msg_id:
        msg_id = last_msg_id + 4
    last_msg_id = msg_id
    return pack("<Q", msg_id)
