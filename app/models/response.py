from typing import Any


class Response:
    def __init__(self, errorStatus: int = 1, message_en: str = "", message_ja: str = "", result: Any = None):
        self.errorStatus = errorStatus
        self.message_en = message_en
        self.message_ja = message_ja
        self.result = result

    def to_dict(self):
        return {
            "errorStatus": self.errorStatus,
            "message": {
                "en": self.message_en,
                "ja": self.message_ja
            },
            "result": self.result,
        }
