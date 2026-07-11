"""Obsidian markdown notes → typable lines.

A line of a note is a paragraph (Obsidian keeps a paragraph on one line and
soft-wraps it). "rendered" (the default) strips the markup — you type what you
see in reading mode. "raw" types the source (frontmatter is always dropped).

Never typed: frontmatter, image embeds, tables, formulas, bare URLs, emoji and
the markup characters themselves. Kept: text, list markers ("- item"), the
contents of ordinary code blocks (without the ``` fences), headings without
their hashes, #tags. Leading indents are kept — the engine winds past them
instead of typing them.
"""

import re

from nabor.normalize import normalize

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(\r?\n|\Z)",
                          re.DOTALL)
_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)\s*([\w-]*)")
# plugin blocks: in Obsidian these render as a table or a diagram, not as code —
# typing the query source would be pointless
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
_STASHED = re.compile(r"\x00(\d+)\x00")  # inline code parked during stripping
_INLINE_MATH = re.compile(r"\$[^$\n]+\$")
_HTML = re.compile(r"</?[a-zA-Z][^>]*>")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)])")
_EMPHASIS = (
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"\*(.+?)\*"), r"\1"),
    (re.compile(r"(?<!\w)_(.+?)_(?!\w)"), r"\1"),  # leave snake_case alone
    (re.compile(r"==(.+?)=="), r"\1"),
    (re.compile(r"~~(.+?)~~"), r"\1"),
)

_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),  # emoji and pictographs
    (0x2190, 0x21FF),    # arrows
    (0x2300, 0x23FF),    # technical symbols
    (0x2600, 0x27BF),    # miscellaneous, dingbats
    (0x2B00, 0x2BFF),    # shapes
    (0xFE00, 0xFE0F),    # variation selectors (emoji presentation)
    (0x200D, 0x200D),    # ZWJ — glues compound emoji together
    (0xFFFC, 0xFFFC),    # object replacement — left behind by Obsidian embeds
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
    # inline code goes behind a placeholder: its backticks are not typed, but
    # what is inside them is not markup either — Obsidian shows `__init__` and
    # `<div>` as they are, so emphasis and HTML must not touch them
    code = []  # type: list[str]

    def stash(m):
        code.append(m.group(1))
        return f"\x00{len(code) - 1}\x00"

    text = _INLINE_CODE.sub(stash, text)
    for pattern, repl in _EMPHASIS:
        text = pattern.sub(repl, text)
    text = text.replace("`", "")  # orphaned backticks (an emoji lived inside)
    text = _HTML.sub("", text)
    if code:
        text = _STASHED.sub(lambda m: code[int(m.group(1))], text)
    # whatever was dropped (emoji, links) leaves a hole: "a task with , while"
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def md_to_lines(raw, table=None, mode="rendered"):
    # type: (str, dict[str, str] | None, str) -> list[str]
    raw = _FRONTMATTER.sub("", raw)
    render = mode != "raw"
    out = []  # type: list[str]
    in_code = False
    skip_code = False  # a plugin block — not even its contents get typed
    in_math = False

    for line in raw.splitlines():
        fence = _FENCE.match(line)
        line = _EMOJI.sub("", line.replace("\t", "    "))

        if fence:
            in_code = not in_code
            skip_code = in_code and fence.group(1).lower() in _PLUGIN_LANGS
            if render:
                continue  # fences are wrapping, not text
        elif in_code:
            if render:
                if skip_code:
                    continue
                # code is typed as written: spaces matter, there is no markup
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
            line = _TASK.sub(r"\1", line)  # "- [ ] task" → "- task"
            indent, body = _split_indent(line)
            body = normalize(_strip_markup(body), table)
            # an indent only matters on nested lists; on prose it is a stray
            # space from the editor, and there is no point typing it
            if not _LIST_ITEM.match(body):
                indent = ""
            line = indent + body if body else ""

        if not render:
            line = normalize(line, table, collapse=False)
        if line.strip():
            out.append(line)

    return out
