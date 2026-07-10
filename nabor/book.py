"""Модель книги и парсеры fb2/txt.

Book → Chapter → абзацы (уже нормализованные строки). Печатаемый поток
главы — абзацы, соединённые '\n' (Enter на границе абзаца). Заголовки
глав не печатаются — показываются баннером.
"""

import re
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from nabor.normalize import normalize

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"

# абзац только из */-/~/=/• и пробелов — декоративный разделитель, не печатается
_SEPARATOR = re.compile(r"^[\s*\-~=•.]+$")


@dataclass
class Chapter:
    title: str
    paragraphs: list = field(default_factory=list)  # type: list[str]

    @property
    def text(self):
        # type: () -> str
        """Печатаемый поток главы; '\\n' — символ конца абзаца."""
        return "\n".join(self.paragraphs)


@dataclass
class Book:
    title: str
    chapters: list  # type: list[Chapter]
    path: Path

    @property
    def text_hash(self):
        # type: () -> str
        h = hashlib.sha256()
        for ch in self.chapters:
            h.update(ch.text.encode())
            h.update(b"\x00")
        return h.hexdigest()


def load_book(path, table=None):
    # type: (str | Path, dict[str, str] | None) -> Book
    path = Path(path)
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".txt"):
        return _load_txt(path, table)
    if suffixes.endswith((".fb2", ".fb2.zip", ".zip")):
        return _load_fb2(path, table)
    raise ValueError(f"Неизвестный формат: {path.name}")


# --- txt ---------------------------------------------------------------

def _load_txt(path, table=None):
    # type: (Path, dict[str, str] | None) -> Book
    raw = path.read_text(encoding="utf-8")
    paragraphs = [normalize(p, table) for p in re.split(r"\n\s*\n", raw)]
    paragraphs = [p for p in paragraphs if p and not _SEPARATOR.match(p)]
    chapter = Chapter(title=path.stem, paragraphs=paragraphs)
    return Book(title=path.stem, chapters=[chapter], path=path)


# --- fb2 ---------------------------------------------------------------

def _fb2_bytes(path):
    # type: (Path) -> bytes
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".fb2")]
            if not names:
                raise ValueError(f"В архиве нет .fb2: {path.name}")
            return z.read(names[0])
    return path.read_bytes()


def _tag(el):
    # type: (ET.Element) -> str
    return el.tag.rsplit("}", 1)[-1]


def _text_of(el):
    # type: (ET.Element) -> str
    return " ".join("".join(el.itertext()).split())


def _section_title(section):
    # type: (ET.Element) -> str
    title_el = section.find(f"{{{FB2_NS}}}title")
    return _text_of(title_el) if title_el is not None else ""


def _section_paragraphs(section, table):
    # type: (ET.Element, dict[str, str] | None) -> list[str]
    """Абзацы секции без захода во вложенные секции; title/image/empty-line
    пропускаются, poem/cite/epigraph дают текст построчно."""
    out = []  # type: list[str]
    for el in section:
        tag = _tag(el)
        if tag in ("title", "image", "empty-line", "section", "annotation"):
            continue
        if tag == "p" or tag == "subtitle":
            p = normalize(_text_of(el), table)
            if p and not _SEPARATOR.match(p):
                out.append(p)
        elif tag in ("poem", "cite", "epigraph"):
            for sub in el.iter():
                if _tag(sub) in ("p", "v", "text-author", "subtitle"):
                    p = normalize(_text_of(sub), table)
                    if p and not _SEPARATOR.match(p):
                        out.append(p)
    return out


def _walk_sections(section, prefix, table, chapters):
    # type: (ET.Element, str, dict[str, str] | None, list[Chapter]) -> None
    title = normalize(_section_title(section), table)
    full_title = f"{prefix} / {title}" if prefix and title else (title or prefix)
    subsections = [el for el in section if _tag(el) == "section"]
    paragraphs = _section_paragraphs(section, table)
    if paragraphs:
        chapters.append(Chapter(title=full_title or f"Раздел {len(chapters) + 1}",
                                paragraphs=paragraphs))
    for sub in subsections:
        _walk_sections(sub, full_title, table, chapters)


def _load_fb2(path, table=None):
    # type: (Path, dict[str, str] | None) -> Book
    root = ET.fromstring(_fb2_bytes(path))
    ns = {"fb": FB2_NS}

    title_el = root.find("fb:description/fb:title-info/fb:book-title", ns)
    book_title = normalize(_text_of(title_el), table) if title_el is not None \
        else path.stem

    chapters = []  # type: list[Chapter]
    for body in root.findall("fb:body", ns):
        if body.get("name") == "notes":
            continue
        for section in body.findall("fb:section", ns):
            _walk_sections(section, "", table, chapters)

    if not chapters:
        raise ValueError(f"Не нашёл ни одной главы с текстом: {path.name}")
    return Book(title=book_title, chapters=chapters, path=path)
