"""Typography normalization: book text is reduced to what a keyboard can
actually type. What you see is what you type."""

import re

# book character → what we show and type (the value may be several characters)
DEFAULT_TABLE = {
    "—": "-",    # em dash
    "–": "-",    # en dash
    "−": "-",    # minus sign
    "«": '"',    # guillemets, both flavours of curly quotes below
    "»": '"',
    "„": '"',
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "…": "...",  # ellipsis
    " ": " ",    # nbsp
    " ": " ",    # thin space
    "­": "",     # soft hyphen
    "ё": "е",    # Russian yo → ye: nobody types it, most books skip it anyway
    "Ё": "Е",
}

_WS_RUN = re.compile(r"\s+")

# cache of translate tables: normalize runs on every paragraph with the same dict
_prepared = {}  # type: dict[int, dict[int, str]]


def normalize(text, table=None, collapse=True):
    # type: (str, dict[str, str] | None, bool) -> str
    """collapse=False keeps whitespace as-is — for code and list indents in
    notes, where alignment carries meaning."""
    table = DEFAULT_TABLE if table is None else table
    trans = _prepared.get(id(table))
    if trans is None:
        trans = {ord(k): v for k, v in table.items()}
        _prepared[id(table)] = trans
    text = text.translate(trans)
    if not collapse:
        return text.rstrip()
    return _WS_RUN.sub(" ", text).strip()
