"""Versioned subtitle rows: late translations patch their original row only."""
from collections import OrderedDict
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CaptionUpdate:
    segment_id: int
    revision: int
    source_text: str = ""
    traditional_chinese_text: str = ""
    state: str = "partial"
    recognition_seconds: float = 0.0
    translation_seconds: float = 0.0
    since_start_seconds: float = 0.0
    after_speech_seconds: float = 0.0
    is_final: bool = False


class CaptionStore:
    def __init__(self, limit=6):
        self.limit = limit
        self.rows = OrderedDict()
        self.latest_id = 0

    def clear(self):
        self.rows.clear()
        self.latest_id = 0

    def apply(self, update: CaptionUpdate) -> bool:
        previous = self.rows.get(update.segment_id)
        if update.state in ("translated", "skipped", "error"):
            if previous is None or update.revision < previous.revision:
                return False
            if update.state in ("translated", "error") and previous.revision != update.revision:
                return False
            update = replace(update, source_text=previous.source_text)
        elif previous:
            if update.revision < previous.revision:
                return False
            if update.revision == previous.revision and previous.state != "partial":
                return False
        elif update.segment_id <= self.latest_id:
            return False
        self.latest_id = max(self.latest_id, update.segment_id)
        self.rows[update.segment_id] = update
        while len(self.rows) > self.limit:
            self.rows.popitem(last=False)
        return True


def translation_line(row: CaptionUpdate) -> str:
    if row.traditional_chinese_text:
        return row.traditional_chinese_text + ("" if row.is_final else "（暫譯）")
    return {
        "partial": "辨識中…", "recognized": "翻譯中…",
        "skipped": "已略過此段翻譯", "error": "本段翻譯失敗",
    }.get(row.state, "")
