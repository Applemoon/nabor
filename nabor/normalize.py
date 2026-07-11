"""Нормализация типографики: текст книги приводится к тому, что реально
набирается с клавиатуры. Видишь = печатаешь."""

import re

# символ книги → что показываем и печатаем (значение может быть многосимвольным)
DEFAULT_TABLE = {
    "—": "-",    # — em dash
    "–": "-",    # – en dash
    "−": "-",    # − minus
    "«": '"',    # «
    "»": '"',    # »
    "„": '"',    # „
    "“": '"',    # “
    "”": '"',    # ”
    "‘": "'",    # ‘
    "’": "'",    # ’
    "…": "...",  # …
    " ": " ",    # nbsp
    " ": " ",    # thin space
    "­": "",     # soft hyphen
    "ё": "е",
    "Ё": "Е",
}

_WS_RUN = re.compile(r"\s+")

# кэш translate-словаря: normalize зовётся на каждый абзац с одной и той же таблицей
_prepared = {}  # type: dict[int, dict[int, str]]


def normalize(text, table=None, collapse=True):
    # type: (str, dict[str, str] | None, bool) -> str
    """collapse=False сохраняет пробелы как есть — для кода и отступов в
    заметках, где выравнивание значимо."""
    table = DEFAULT_TABLE if table is None else table
    trans = _prepared.get(id(table))
    if trans is None:
        trans = {ord(k): v for k, v in table.items()}
        _prepared[id(table)] = trans
    text = text.translate(trans)
    if not collapse:
        return text.rstrip()
    return _WS_RUN.sub(" ", text).strip()
