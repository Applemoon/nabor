"""Textual-приложение: экран набора (окно строк с курсором по центру),
статус-бар, футер с хоткеями, полка книг."""

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from nabor import storage, theme
from nabor.book import load_book
from nabor.engine import Engine, Result

BOOK_GLOBS = ("*.fb2", "*.fb2.zip", "*.zip", "*.txt")


def wrap_offsets(text, width):
    # type: (str, int) -> list[tuple[int, int]]
    """Строки как (start, end) в тексте главы; каждый символ (включая
    пробел на переносе и '\\n') принадлежит ровно одной строке."""
    lines = []
    pos = 0
    for para in text.split("\n"):
        start = pos
        para_end = pos + len(para)
        while para_end - start > width:
            cut = text.rfind(" ", start, start + width)
            if cut <= start:
                cut = start + width - 1  # слово длиннее строки — жёсткий разрез
            lines.append((start, cut + 1))
            start = cut + 1
        end = para_end + (1 if para_end < len(text) else 0)  # '\n' — в строку
        lines.append((start, end))
        pos = para_end + 1
    return lines


class TypingArea(Static):
    """Окно текста: window_lines строк, строка с курсором по центру."""

    engine = None  # type: Engine | None

    def __init__(self, window_lines):
        super().__init__()
        self.window_lines = window_lines
        self._cache_key = None
        self._lines = []  # type: list[tuple[int, int]]

    def _wrapped(self, width):
        # type: (int) -> list[tuple[int, int]]
        key = (self.engine.chapter_idx, len(self.engine.text), width)
        if key != self._cache_key:
            self._lines = wrap_offsets(self.engine.text, width)
            self._cache_key = key
        return self._lines

    def render(self):
        e = self.engine
        if e is None:
            return ""
        width = max(20, self.size.width - 4)
        lines = self._wrapped(width)
        cursor_pos = min(e.offset + len(e.tail), len(e.text))

        cur_line = 0
        for i, (start, end) in enumerate(lines):
            if start <= cursor_pos < end or (cursor_pos == len(e.text)
                                             and i == len(lines) - 1):
                cur_line = i
                break

        half = self.window_lines // 2
        out = Text(no_wrap=True, end="")
        for i in range(cur_line - half, cur_line - half + self.window_lines):
            if i != cur_line - half:
                out.append("\n")
            if not 0 <= i < len(lines):
                continue
            start, end = lines[i]
            for pos in range(start, end):
                ch = e.text[pos]
                shown = "¶" if ch == "\n" else ch
                if pos < e.offset:
                    style = theme.DIM if ch == "\n" else theme.TYPED
                elif pos < e.offset + len(e.tail):
                    wrong = e.tail[pos - e.offset]
                    shown = "¶" if wrong == "\n" else (wrong if wrong.isprintable() and wrong != " " else shown)
                    style = theme.MISTAKE
                elif pos == cursor_pos:
                    style = theme.CURSOR
                else:
                    style = theme.DIM if ch == "\n" else theme.UNTYPED
                out.append(shown, style)
            if cursor_pos == len(e.text) and i == len(lines) - 1:
                out.append(" ", theme.CURSOR)  # курсор за последним символом
        return out


class StatusBar(Horizontal):
    def compose(self):
        # type: () -> ComposeResult
        yield Static(id="status-left")
        yield Static(id="status-right")

    def update_status(self, engine, book):
        # type: (Engine, object) -> None
        n = len(book.chapters)
        left = (f" {book.title} · Гл. {engine.chapter_idx + 1}/{n}"
                f" · {engine.percent:.1f}%")
        s = engine.stats
        right = f"{s.wpm_now:.0f} wpm · {s.accuracy:.0f}% "
        self.query_one("#status-left", Static).update(left)
        self.query_one("#status-right", Static).update(right)


class TypingScreen(Screen):
    AUTO_FOCUS = None
    BINDINGS = [
        Binding("escape", "app.quit", "Выход"),
        Binding("left", "prev_sentence", "←предл", key_display="←"),
        Binding("right", "next_sentence", "предл→", key_display="→"),
        Binding("up", "prev_paragraph", "↑абзац", key_display="↑"),
        Binding("down", "next_paragraph", "абзац↓", key_display="↓"),
        Binding("pageup", "prev_chapter", "глава", key_display="⇞"),
        Binding("pagedown", "next_chapter", "глава", key_display="⇟"),
        Binding("ctrl+b", "app.shelf", "Полка"),
    ]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(id="banner")
        yield TypingArea(self.app.cfg["window_lines"])
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self):
        # type: () -> None
        self.query_one(TypingArea).engine = self.app.engine
        self.refresh_all()
        self.set_interval(1.0, self.update_status)

    # --- ввод ---

    def on_key(self, event):
        # type: (object) -> None
        e = self.app.engine
        if e is None:
            return
        if event.key == "backspace":
            e.backspace()
        elif event.key == "enter":
            self._type("\n")
        elif event.is_printable and event.character:
            self._type(event.character)
        else:
            return  # служебные клавиши — в биндинги
        event.stop()
        self.refresh_all()

    def _type(self, ch):
        # type: (str) -> None
        result = self.app.engine.type_char(ch)
        if result == Result.DONE:
            if self.app.engine.book_done:
                self.notify("Книга закончена! 🎉", timeout=10)
                self.app.save_position()
            else:
                self.app.engine.next_chapter()
                self.app.save_position()

    # --- навигация ---

    def _nav(self, method):
        # type: (str) -> None
        getattr(self.app.engine, method)()
        self.app.save_position()
        self.refresh_all()

    def action_prev_sentence(self): self._nav("prev_sentence")
    def action_next_sentence(self): self._nav("next_sentence")
    def action_prev_paragraph(self): self._nav("prev_paragraph")
    def action_next_paragraph(self): self._nav("next_paragraph")
    def action_prev_chapter(self): self._nav("prev_chapter")
    def action_next_chapter(self): self._nav("next_chapter")

    # --- отрисовка ---

    def refresh_all(self):
        # type: () -> None
        e = self.app.engine
        self.query_one("#banner", Static).update(
            Text(e.chapter.title, style=f"bold {theme.YELLOW}",
                 justify="center"))
        self.query_one(TypingArea).refresh()
        self.update_status()

    def update_status(self):
        # type: () -> None
        self.query_one(StatusBar).update_status(self.app.engine,
                                                self.app.book)


class ShelfScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Назад")]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(Text("Полка", style=f"bold {theme.YELLOW}",
                          justify="center"), id="banner")
        yield OptionList(id="shelf")
        yield Footer()

    def on_mount(self):
        # type: () -> None
        ol = self.query_one(OptionList)
        progress = storage.load_progress()
        books = self.app.library_books()
        if not books:
            ol.add_option(Option("Библиотека пуста — положи fb2/txt в library/",
                                 disabled=True))
            return
        books.sort(key=lambda p: progress.get(p.name, {}).get("last_opened", ""),
                   reverse=True)
        for path in books:
            entry = progress.get(path.name, {})
            pct = entry.get("percent", 0)
            opened = entry.get("last_opened", "")[:10] or "—"
            label = f"{path.stem}  ·  {pct}%  ·  {opened}"
            ol.add_option(Option(label, id=str(path)))

    def on_option_list_option_selected(self, event):
        # type: (object) -> None
        self.app.open_book(Path(event.option.id))

    def action_back(self):
        # type: () -> None
        if self.app.engine is not None:
            self.app.pop_screen()
        else:
            self.app.exit()


class NaborApp(App):
    TITLE = "nabor"
    ENABLE_COMMAND_PALETTE = False
    CSS = f"""
    Screen {{
        background: {theme.BG};
        color: {theme.FG};
    }}
    #banner {{
        height: 3;
        content-align: center bottom;
        padding: 1 2 0 2;
    }}
    TypingArea {{
        width: 100%;
        height: 1fr;
        content-align: center middle;
        padding: 0 2;
    }}
    #status {{
        height: 1;
        background: {theme.BG1};
        color: {theme.GRAY};
    }}
    #status-left {{ width: 1fr; }}
    #status-right {{ width: auto; }}
    #shelf {{
        height: 1fr;
        margin: 1 2;
        background: {theme.BG};
    }}
    Footer {{
        background: {theme.BG1};
    }}
    """

    def __init__(self, cfg, book_path=None):
        # type: (dict, Path | None) -> None
        super().__init__()
        self.cfg = cfg
        self._start_path = book_path
        self.book = None
        self.engine = None  # type: Engine | None

    def library_books(self):
        # type: () -> list[Path]
        lib = Path(self.cfg["library_dir"])
        books = []
        for pattern in BOOK_GLOBS:
            books.extend(lib.glob(pattern))
        return sorted(set(books))

    def on_mount(self):
        # type: () -> None
        path = self._start_path
        if path is None:
            last = storage.last_opened_book()
            if last:
                candidates = [p for p in self.library_books() if p.name == last]
                path = candidates[0] if candidates else None
        if path is not None:
            self.open_book(path)
        else:
            self.push_screen(ShelfScreen())
        self.set_interval(30.0, self.save_position)

    def open_book(self, path):
        # type: (Path) -> None
        self.finish_session()
        self.book = load_book(path, self.cfg["normalize"])
        chapter, offset, hash_ok = storage.get_position(self.book)
        self.engine = Engine(self.book, chapter, offset,
                             error_tail_max=self.cfg["error_tail_max"],
                             idle_timeout=self.cfg["idle_timeout"])
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self.push_screen(TypingScreen())
        if not hash_ok:
            self.notify("Текст книги изменился — позиция сброшена "
                        "на начало главы", severity="warning", timeout=8)

    def save_position(self):
        # type: () -> None
        if self.engine is not None:
            storage.save_position(self.book, self.engine.chapter_idx,
                                  self.engine.offset, self.engine.percent)

    def finish_session(self):
        # type: () -> None
        if self.engine is not None:
            self.save_position()
            storage.append_session(
                self.engine.stats.session_record(self.book.title))
            self.engine = None

    def action_shelf(self):
        # type: () -> None
        if not isinstance(self.screen, ShelfScreen):
            self.push_screen(ShelfScreen())

    async def action_quit(self):
        # type: () -> None
        self.finish_session()
        self.exit()
