"""Textual-приложение: экран набора (окно строк с курсором по центру),
статус-бар, футер с хоткеями, полка книг."""

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from rich import box
from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
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

    def __init__(self, window_lines, cursor_style):
        super().__init__()
        self.window_lines = window_lines
        self.cursor_style = cursor_style
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
                    style = self.cursor_style
                else:
                    style = theme.DIM if ch == "\n" else theme.UNTYPED
                out.append(shown, style)
            if cursor_pos == len(e.text) and i == len(lines) - 1:
                out.append(" ", self.cursor_style)  # курсор за последним символом
        return out


class BookProgress(Static):
    """Полноширинный прогресс-бар книги."""

    engine = None  # type: Engine | None

    def render(self):
        if self.engine is None:
            return ""
        width = max(10, self.size.width)
        filled = round(width * self.engine.percent / 100)
        out = Text(no_wrap=True, end="")
        out.append("━" * filled, theme.ORANGE)
        out.append("━" * (width - filled), theme.BG2)
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
        right = (f"{s.cpm_now:.0f} зн/мин · {s.wpm_now:.0f} wpm"
                 f" · {s.accuracy:.0f}% ")
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
        Binding("ctrl+s", "app.stats", "Статистика"),
    ]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(id="banner")
        cursor = theme.CURSOR_BLOCK if self.app.cfg["cursor"] == "block" \
            else theme.CURSOR_LINE
        yield TypingArea(self.app.cfg["window_lines"], cursor)
        yield BookProgress(id="book-progress")
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self):
        # type: () -> None
        self.query_one(TypingArea).engine = self.app.engine
        self.query_one(BookProgress).engine = self.app.engine
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
        self.query_one(BookProgress).refresh()


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


class StatsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Назад")]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(Text("Статистика", style=f"bold {theme.YELLOW}",
                          justify="center"), id="banner")
        with VerticalScroll(id="stats-scroll"):
            yield Static(id="stats-body")
        yield Footer()

    def on_mount(self):
        # type: () -> None
        self.query_one("#stats-body", Static).update(self._build())

    def _build(self):
        sessions = storage.read_sessions()
        live = None
        if self.app.engine is not None:
            live = self.app.engine.stats.session_record(self.app.book.title)
            if live:
                sessions.append(live)
        if not sessions:
            return Text("Пока пусто — напечатай что-нибудь.", style=theme.GRAY)

        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        def row(label, sel):
            active = sum(s["active_sec"] for s in sel)
            chars = sum(s["chars"] for s in sel)
            errors = sum(s["errors"] for s in sel)
            cpm = chars / (active / 60) if active else 0
            acc = chars / (chars + errors) * 100 if chars + errors else 100
            return (label, str(len(sel)), f"{active / 60:.0f} мин",
                    f"{chars}", f"{cpm:.0f}", f"{cpm / 5:.0f}", f"{acc:.0f}%")

        totals = Table(box=box.SIMPLE_HEAD, header_style=theme.GRAY,
                       style=theme.FG, pad_edge=False)
        for col in ("", "сессий", "время", "знаков", "зн/мин", "wpm", "точн."):
            totals.add_column(col, justify="right" if col else "left")
        totals.add_row(*row("Сегодня",
                            [s for s in sessions if s["ts"] >= today]))
        totals.add_row(*row("7 дней",
                            [s for s in sessions if s["ts"] >= week_ago]))
        totals.add_row(*row("Всё время", sessions))

        errs = Counter()  # type: Counter[str]
        for s in sessions:
            errs.update(s.get("char_errors", {}))
        show = {" ": "␣", "\n": "¶"}
        top = "  ".join(f"{show.get(c, c)}×{n}" for c, n in errs.most_common(10))
        errors_line = Text.assemble(
            ("Промахи по символам:  ", theme.GRAY),
            (top or "нет", f"bold {theme.RED if top else theme.GREEN}"))

        last = Table(box=box.SIMPLE_HEAD, header_style=theme.GRAY,
                     style=theme.FG, pad_edge=False,
                     title="Последние сессии", title_style=theme.GRAY)
        for col, j in (("когда", "left"), ("книга", "left"), ("мин", "right"),
                       ("знаков", "right"), ("зн/мин", "right"),
                       ("wpm", "right"), ("точн.", "right")):
            last.add_column(col, justify=j)
        for s in sessions[-10:][::-1]:
            when = "▸ сейчас" if s is live else \
                s["ts"][5:16].replace("T", " ").replace("-", ".")
            cpm = s["chars"] / (s["active_sec"] / 60) if s["active_sec"] else 0
            last.add_row(when, s["book"][:30], f"{s['active_sec'] / 60:.0f}",
                         str(s["chars"]), f"{cpm:.0f}", f"{cpm / 5:.0f}",
                         f"{s['accuracy']:.0f}%",
                         style=theme.AQUA if s is live else None)

        return Group(totals, Text(), errors_line, Text(), last)

    def action_back(self):
        # type: () -> None
        self.app.pop_screen()


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
    #book-progress {{
        height: 1;
    }}
    #status {{
        height: 1;
        background: {theme.BG1};
        color: {theme.GRAY};
    }}
    #stats-scroll {{
        height: 1fr;
        margin: 1 4;
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

    def action_stats(self):
        # type: () -> None
        if not isinstance(self.screen, StatsScreen):
            self.push_screen(StatsScreen())

    async def action_quit(self):
        # type: () -> None
        self.finish_session()
        self.exit()
