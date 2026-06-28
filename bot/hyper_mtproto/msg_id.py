import time
from struct import pack


class MsgId:
    last_time = 0
    offset = 0

    @classmethod
    def generate(cls):
        now = int(time.time())
        cls.offset = (cls.offset + 4) if now == cls.last_time else 0
        msg_id = (now << 32) + cls.offset
        cls.last_time = now
        return pack("<q", msg_id)


generate_msg_id = MsgId.generate
