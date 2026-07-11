"""Модель книги и парсеры fb2/txt/md.

Book → Chapter → абзацы (уже нормализованные строки). Печатаемый поток
главы — абзацы, соединённые '\n' (Enter на границе абзаца). Заголовки
глав не печатаются — показываются баннером.

Заметка Obsidian (.md) — книга из одной главы: разовое упражнение, прогресс
для неё не пишется (см. random_note).
"""

import re
import random
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from nabor.markdown import md_to_lines
from nabor.normalize import normalize

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"

# абзац только из */-/~/=/• и пробелов — декоративный разделитель, не печатается
_SEPARATOR = re.compile(r"^[\s*\-~=•.]+$")


def _keeper(skip_paragraphs=()):
    # type: (tuple[str, ...]) -> object
    """Предикат «этот абзац печатаем»: не пустой, не разделитель и не подходит
    ни под один regex из skip_paragraphs (издательские врезки — см. config)."""
    patterns = [re.compile(p, re.IGNORECASE) for p in skip_paragraphs]

    def keep(p):
        # type: (str) -> bool
        if not p or _SEPARATOR.match(p):
            return False
        return not any(pat.search(p) for pat in patterns)

    return keep


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


def load_book(path, table=None, skip_epigraphs=False, skip_paragraphs=(),
              markdown="rendered"):
    # type: (str | Path, dict[str, str] | None, bool, tuple[str, ...], str) -> Book
    path = Path(path)
    keep = _keeper(skip_paragraphs)
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".txt"):
        return _load_txt(path, table, keep)
    if suffixes.endswith(".md"):
        return _load_md(path, table, keep, markdown)
    if suffixes.endswith((".fb2", ".fb2.zip", ".zip")):
        return _load_fb2(path, table, skip_epigraphs, keep)
    raise ValueError(f"Неизвестный формат: {path.name}")


# --- заметки Obsidian (.md) --------------------------------------------

def _load_md(path, table=None, keep=None, markdown="rendered"):
    # type: (Path, dict[str, str] | None, object, str) -> Book
    keep = keep or _keeper()
    lines = md_to_lines(path.read_text(encoding="utf-8"), table, markdown)
    # keep() зовём на текст без отступа: ведущие пробелы значимы, но на
    # «пустая или разделитель» не влияют
    lines = [ln for ln in lines if keep(ln.strip())]
    return Book(title=path.stem, path=path,
                chapters=[Chapter(title=path.stem, paragraphs=lines)])


def vault_notes(vault_dir, exclude=()):
    # type: (str | Path, tuple[str, ...]) -> list[Path]
    """Все .md хранилища, кроме скрытых (.obsidian, .trash) и exclude —
    имён верхних папок или файлов в корне."""
    root = Path(vault_dir).expanduser()
    notes = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if rel.parts[0] in exclude:
            continue
        notes.append(path)
    return sorted(notes)


def random_note(vault_dir, exclude=(), min_chars=0, table=None,
                markdown="rendered", skip_paragraphs=(), besides=None):
    # type: (str | Path, tuple[str, ...], int, dict[str, str] | None, str, tuple[str, ...], Path | None) -> Book
    """Случайная заметка длиннее min_chars (короткие — не упражнение).
    besides — заметка, которую только что набирали: не повторяем."""
    notes = vault_notes(vault_dir, exclude)
    if besides is not None and len(notes) > 1:
        notes = [p for p in notes if p != besides]
    if not notes:
        raise ValueError(f"В хранилище нет заметок: {vault_dir}")
    keep = _keeper(skip_paragraphs)
    random.shuffle(notes)
    for path in notes:
        book = _load_md(path, table, keep, markdown)
        if len(book.chapters[0].text) >= min_chars:
            return book
    raise ValueError(f"Все заметки короче {min_chars} знаков")


# --- txt ---------------------------------------------------------------

def _load_txt(path, table=None, keep=None):
    # type: (Path, dict[str, str] | None, object) -> Book
    keep = keep or _keeper()
    raw = path.read_text(encoding="utf-8")
    paragraphs = [normalize(p, table) for p in re.split(r"\n\s*\n", raw)]
    paragraphs = [p for p in paragraphs if keep(p)]
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


def _section_paragraphs(section, table, skip_epigraphs, keep):
    # type: (ET.Element, dict[str, str] | None, bool, object) -> list[str]
    """Абзацы секции без захода во вложенные секции; title/image/empty-line
    пропускаются, poem/cite/epigraph дают текст построчно. skip_epigraphs
    выкидывает <epigraph> целиком (в HPMOR там шутки-дисклеймеры)."""
    out = []  # type: list[str]
    for el in section:
        tag = _tag(el)
        if tag in ("title", "image", "empty-line", "section", "annotation"):
            continue
        if skip_epigraphs and tag == "epigraph":
            continue
        if tag == "p" or tag == "subtitle":
            p = normalize(_text_of(el), table)
            if keep(p):
                out.append(p)
        elif tag in ("poem", "cite", "epigraph"):
            for sub in el.iter():
                if _tag(sub) in ("p", "v", "text-author", "subtitle"):
                    p = normalize(_text_of(sub), table)
                    if keep(p):
                        out.append(p)
    return out


def _walk_sections(section, prefix, table, chapters, skip_epigraphs, keep):
    # type: (ET.Element, str, dict[str, str] | None, list[Chapter], bool, object) -> None
    title = normalize(_section_title(section), table)
    full_title = f"{prefix} / {title}" if prefix and title else (title or prefix)
    subsections = [el for el in section if _tag(el) == "section"]
    paragraphs = _section_paragraphs(section, table, skip_epigraphs, keep)
    if paragraphs:
        chapters.append(Chapter(title=full_title or f"Раздел {len(chapters) + 1}",
                                paragraphs=paragraphs))
    for sub in subsections:
        _walk_sections(sub, full_title, table, chapters, skip_epigraphs, keep)


def _load_fb2(path, table=None, skip_epigraphs=False, keep=None):
    # type: (Path, dict[str, str] | None, bool, object) -> Book
    keep = keep or _keeper()
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
            _walk_sections(section, "", table, chapters, skip_epigraphs, keep)

    if not chapters:
        raise ValueError(f"Не нашёл ни одной главы с текстом: {path.name}")
    return Book(title=book_title, chapters=chapters, path=path)
