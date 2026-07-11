"""Book model and the fb2/txt/md parsers.

Book → Chapter → paragraphs (already normalized strings). A chapter's typing
stream is its paragraphs joined by '\n' (Enter is the character that ends a
paragraph). Chapter titles are not typed — they are shown as a banner.

An Obsidian note (.md) is a one-chapter book: a one-off exercise, no progress
is saved for it (see random_note).
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

# a paragraph of nothing but */-/~/=/• and spaces is a decorative divider —
# it is not typed
_SEPARATOR = re.compile(r"^[\s*\-~=•.]+$")


def _keeper(skip_paragraphs=()):
    # type: (tuple[str, ...]) -> object
    """Predicate "this paragraph gets typed": not empty, not a divider, and
    matching none of the skip_paragraphs regexes (publisher ads — see config)."""
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
        """The chapter's typing stream; '\\n' ends a paragraph."""
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
    raise ValueError(f"Unknown format: {path.name}")


# --- Obsidian notes (.md) ----------------------------------------------

def _load_md(path, table=None, keep=None, markdown="rendered"):
    # type: (Path, dict[str, str] | None, object, str) -> Book
    keep = keep or _keeper()
    lines = md_to_lines(path.read_text(encoding="utf-8"), table, markdown)
    # keep() is called on the text without its indent: leading spaces matter for
    # typing, but not for the "empty or a divider" verdict
    lines = [ln for ln in lines if keep(ln.strip())]
    return Book(title=path.stem, path=path,
                chapters=[Chapter(title=path.stem, paragraphs=lines)])


def vault_notes(vault_dir, exclude=()):
    # type: (str | Path, tuple[str, ...]) -> list[Path]
    """Every .md in the vault except hidden ones (.obsidian, .trash) and those
    under exclude — names of top-level folders or of files in the root."""
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
    """A random note longer than min_chars (short ones are no exercise).
    besides — the note just typed: do not serve it twice in a row."""
    notes = vault_notes(vault_dir, exclude)
    if besides is not None and len(notes) > 1:
        notes = [p for p in notes if p != besides]
    if not notes:
        raise ValueError(f"No notes in the vault: {vault_dir}")
    keep = _keeper(skip_paragraphs)
    random.shuffle(notes)
    for path in notes:
        book = _load_md(path, table, keep, markdown)
        if len(book.chapters[0].text) >= min_chars:
            return book
    raise ValueError(f"Every note is shorter than {min_chars} characters")


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
                raise ValueError(f"No .fb2 inside the archive: {path.name}")
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
    """Paragraphs of a section, without descending into nested sections;
    title/image/empty-line are dropped, poem/cite/epigraph yield their text line
    by line. skip_epigraphs throws <epigraph> out whole (in HPMOR those hold the
    author's joke disclaimers, which is why they are typed by default)."""
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
        chapters.append(Chapter(title=full_title or f"Part {len(chapters) + 1}",
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
        raise ValueError(f"Not a single chapter with text: {path.name}")
    return Book(title=book_title, chapters=chapters, path=path)
