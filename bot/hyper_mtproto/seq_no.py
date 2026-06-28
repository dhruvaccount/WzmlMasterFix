from struct import pack


class SeqNo:
    def __init__(self):
        self.content_messages = 0

    def __call__(self, is_content=True):
        if is_content:
            result = self.content_messages * 2 + 1
            self.content_messages += 1
        else:
            result = self.content_messages * 2
        return pack("<I", result)
