from struct import pack


class SeqNo:
    def __init__(self):
        self.content_related_messages_sent = 0

    def __call__(self, is_content=True):
        seq_no = (self.content_related_messages_sent * 2) + (1 if is_content else 0)
        if is_content:
            self.content_related_messages_sent += 1
        return pack("<I", seq_no)
