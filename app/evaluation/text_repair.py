from __future__ import annotations

from typing import Any


MOJIBAKE_MARKERS = ("Ã", "Â", "å", "æ", "ç", "é", "è", "ä", "ã", "ð", "閰", "浜", "璁", "绛", "锛", "銆")


def repair_text(value: str) -> str:
    text = str(value or "")
    if not looks_mojibake(text):
        return text
    candidates = [text]
    for encoding in ("latin1", "cp1252"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except UnicodeError:
            continue
    best = min(candidates, key=mojibake_score)
    return best


def repair_nested(value: Any) -> Any:
    if isinstance(value, str):
        return repair_text(value)
    if isinstance(value, list):
        return [repair_nested(item) for item in value]
    if isinstance(value, dict):
        return {key: repair_nested(item) for key, item in value.items()}
    return value


def looks_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS) or has_c1_controls(text)


def mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS) + text.count("\ufffd") * 5 + sum(3 for char in text if is_c1_control(char))


def has_c1_controls(text: str) -> bool:
    return any(is_c1_control(char) for char in text)


def is_c1_control(char: str) -> bool:
    return 0x80 <= ord(char) <= 0x9F
