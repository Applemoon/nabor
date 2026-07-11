"""Markdown-заметки Obsidian → печатаемые строки.

Строка заметки = абзац (Obsidian пишет абзац одной строкой, перенос —
мягкий). "rendered" (дефолт): разметка снимается — печатаешь то, что видишь
в режиме чтения. "raw": печатается исходник (frontmatter выкидывается всегда).

Что не печатается: frontmatter, эмбеды картинок, таблицы, формулы, голые
URL, эмодзи, сами маркеры разметки. Что остаётся: текст, маркеры списков
("- пункт"), содержимое код-блоков (без ```-фенсов), заголовки без решёток,
#теги. Ведущие отступы сохраняются — движок их проматывает, не печатая.
"""

import re

from nabor.normalize import normalize

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(\r?\n|\Z)",
                          re.DOTALL)
_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)\s*([\w-]*)")
# блоки плагинов: в Obsidian это не код, а отрендеренная таблица/диаграмма —
# печатать исходник запроса бессмысленно
_PLUGIN_LANGS = frozenset(("dataview", "dataviewjs", "tasks", "query",
                           "mermaid", "chart", "kanban-plugin", "meta-bind"))
_TABLE_ROW = re.compile(r"^\s{0,3}\|")
_MATH_FENCE = re.compile(r"^\s{0,3}\$\$\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_QUOTE = re.compile(r"^\s{0,3}(>\s?)+")
_CALLOUT_HEAD = re.compile(r"^\[![^\]]+\][+-]?\s*")
_TASK = re.compile(r"^(\s*[-*+]\s+)\[[^\]]\]\s+")
_LIST_ITEM = re.compile(r"^([-*+]|\d+[.)])\s")

_EMBED = re.compile(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)")
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_MDLINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_FOOTNOTE = re.compile(r"\[\^[^\]]+\]")
_BARE_URL = re.compile(r"<?\b(?:https?|obsidian)://\S+>?")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_INLINE_MATH = re.compile(r"\$[^$\n]+\$")
_HTML = re.compile(r"</?[a-zA-Z][^>]*>")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)])")
_EMPHASIS = (
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"\*(.+?)\*"), r"\1"),
    (re.compile(r"(?<!\w)_(.+?)_(?!\w)"), r"\1"),  # snake_case не трогаем
    (re.compile(r"==(.+?)=="), r"\1"),
    (re.compile(r"~~(.+?)~~"), r"\1"),
)

_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),  # эмодзи и пиктограммы
    (0x2190, 0x21FF),    # стрелки
    (0x2300, 0x23FF),    # технические знаки
    (0x2600, 0x27BF),    # разное, дингбаты
    (0x2B00, 0x2BFF),    # фигуры
    (0xFE00, 0xFE0F),    # вариационные селекторы (эмодзи-презентация)
    (0x200D, 0x200D),    # ZWJ — склейка составных эмодзи
    (0xFFFC, 0xFFFC),    # object replacement — след вставки в Obsidian
)
_EMOJI = re.compile(
    "[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in _EMOJI_RANGES) + "]")


def _split_indent(line):
    # type: (str) -> tuple[str, str]
    body = line.lstrip(" ")
    return " " * (len(line) - len(body)), body


def _strip_markup(text):
    # type: (str) -> str
    text = _EMBED.sub("", text)
    text = _WIKILINK.sub(lambda m: m.group(2) or m.group(1), text)
    text = _MDLINK.sub(r"\1", text)
    text = _FOOTNOTE.sub("", text)
    text = _BARE_URL.sub("", text)
    text = _INLINE_MATH.sub("", text)
    text = _INLINE_CODE.sub(r"\1", text)  # до эмфазы: `foo_bar` не станет курсивом
    for pattern, repl in _EMPHASIS:
        text = pattern.sub(repl, text)
    text = text.replace("`", "")  # осиротевшие бэктики (внутри был эмодзи)
    text = _HTML.sub("", text)
    # на месте выкинутого (эмодзи, ссылки) остаётся дыра: "задача с , при"
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def md_to_lines(raw, table=None, mode="rendered"):
    # type: (str, dict[str, str] | None, str) -> list[str]
    raw = _FRONTMATTER.sub("", raw)
    render = mode != "raw"
    out = []  # type: list[str]
    in_code = False
    skip_code = False  # блок плагина — не печатаем даже содержимое
    in_math = False

    for line in raw.splitlines():
        fence = _FENCE.match(line)
        line = _EMOJI.sub("", line.replace("\t", "    "))

        if fence:
            in_code = not in_code
            skip_code = in_code and fence.group(1).lower() in _PLUGIN_LANGS
            if render:
                continue  # фенсы — обёртка, не текст
        elif in_code:
            if render:
                if skip_code:
                    continue
                # код печатается как написан: пробелы значимы, разметки нет
                line = normalize(line, table, collapse=False)
                if line.strip():
                    out.append(line)
                continue
        elif render:
            if _MATH_FENCE.match(line):
                in_math = not in_math
                continue
            if in_math or _TABLE_ROW.match(line):
                continue
            line = _QUOTE.sub("", line)
            line = _CALLOUT_HEAD.sub("", line)
            line = _HEADING.sub("", line)
            line = _TASK.sub(r"\1", line)  # "- [ ] задача" → "- задача"
            indent, body = _split_indent(line)
            body = normalize(_strip_markup(body), table)
            # отступ значим только у вложенных списков; у прозы это случайный
            # пробел из редактора — печатать его незачем
            if not _LIST_ITEM.match(body):
                indent = ""
            line = indent + body if body else ""

        if not render:
            line = normalize(line, table, collapse=False)
        if line.strip():
            out.append(line)

    return out
