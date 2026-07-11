"""progress.json (позиции по книгам) и stats.jsonl (журнал сессий,
append-only)."""

import json
import time
from pathlib import Path

from nabor.config import ROOT

PROGRESS_PATH = ROOT / "progress.json"
STATS_PATH = ROOT / "stats.jsonl"


def load_progress():
    # type: () -> dict
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {}


def save_position(book, chapter, offset, percent=0.0):
    # type: (object, int, int, float) -> None
    progress = load_progress()
    progress[book.path.name] = {
        "chapter": chapter,
        "offset": offset,
        "percent": round(percent, 1),
        "text_hash": book.text_hash,
        "last_opened": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def get_position(book):
    # type: (object) -> tuple[int, int, bool]
    """(chapter, offset, hash_ok). При несовпадении хэша текста —
    позиция в начало сохранённой главы, hash_ok=False (не молча)."""
    entry = load_progress().get(book.path.name)
    if entry is None:
        return 0, 0, True
    if entry.get("text_hash") != book.text_hash:
        return entry.get("chapter", 0), 0, False
    return entry.get("chapter", 0), entry.get("offset", 0), True


def last_opened_book():
    # type: () -> str | None
    """Имя файла книги с самым свежим заходом (для авторезюма)."""
    progress = load_progress()
    if not progress:
        return None
    return max(progress, key=lambda k: progress[k].get("last_opened", ""))


def read_sessions():
    # type: () -> list[dict]
    if not STATS_PATH.exists():
        return []
    out = []
    for line in STATS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def append_session(record):
    # type: (dict | None) -> None
    if not record:
        return
    with open(STATS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def clear_char_errors():
    # type: () -> int
    """Забыть промахи по символам во всех сессиях; скорость, время и
    точность остаются. Возвращает, сколько промахов стёрли."""
    sessions = read_sessions()
    wiped = sum(sum(s.get("char_errors", {}).values()) for s in sessions)
    if not wiped:
        return 0
    for s in sessions:
        s.pop("char_errors", None)
    tmp = STATS_PATH.with_suffix(STATS_PATH.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n"
                           for s in sessions), encoding="utf-8")
    tmp.replace(STATS_PATH)  # атомарно: журнал не порвётся на полуслове
    return wiped
