"""Small, testable presentation rules for the transient subtitle overlay."""
from math import isfinite

DISPLAY_MS = 3000
DEFAULT_POSITION = {"x": 0.5, "y": 0.88}


def single_line(text):
    return " ".join(text.split())


def fit_text(text, width, measure):
    """Keep a single measured line; the main window retains the full text."""
    text = single_line(text)
    if measure(text) <= width:
        return text
    if width < measure("…"):
        return ""
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(text[:mid] + "…") <= width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + "…"


def line_parts(source, target, width, measure):
    """Share one line between original and translation without duplicating Chinese."""
    source, target = single_line(source), single_line(target)
    if not source or not target or source == target:
        return [(fit_text(target or source, width, measure), "white")]
    separator = "  ·  "
    available = max(0, width - measure(separator))
    source_width, target_width = measure(source), measure(target)
    if source_width + target_width > available:
        # Reserve room for both languages, lending unused space to the longer one.
        source_width = min(source_width, max(available * .45, available - target_width))
        target_width = available - source_width
    return [(fit_text(source, source_width, measure), "#d9e7ff"),
            (separator, "#b6c4d6"),
            (fit_text(target, target_width, measure), "white")]


def normalized_position(value):
    if not isinstance(value, dict):
        return dict(DEFAULT_POSITION)
    try:
        x, y = float(value["x"]), float(value["y"])
        if not isfinite(x) or not isfinite(y):
            raise ValueError("Nonfinite position")
        return {"x": min(1, max(0, x)), "y": min(1, max(0, y))}
    except (KeyError, TypeError, ValueError, OverflowError):
        return dict(DEFAULT_POSITION)


def window_position(position, screen_width, screen_height, width, height):
    position = normalized_position(position)
    return (max(0, min(screen_width - width, round(screen_width * position["x"] - width / 2))),
            max(0, min(screen_height - height, round(screen_height * position["y"] - height / 2))))


class LatestCaption:
    """Do not revive expired rows when a translation patches an older segment."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.latest_id = -1
        self.signature = None

    def changed_row(self, rows):
        row = max(rows, key=lambda item: item.segment_id, default=None)
        if row is None or row.segment_id < self.latest_id:
            return None
        self.latest_id = row.segment_id
        signature = (row.segment_id, single_line(row.source_text),
                     single_line(row.traditional_chinese_text))
        if signature == self.signature:
            return None
        self.signature = signature
        return row if signature[1] or signature[2] else None
