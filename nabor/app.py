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
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from nabor import storage, theme
from nabor.book import load_book, random_note
from nabor.config import DEFAULTS, UI_KEYS, save_ui_settings
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


class WrapFooter(Static):
    """Футер с хоткеями текущего экрана; не влезает в ширину — переносит
    блоки на следующие строки (стандартный Footer просто режется)."""

    KEY_LABELS = {"escape": "esc", "enter": "enter"}

    def render(self):
        parts = []
        for b in self.screen.BINDINGS:
            if isinstance(b, Binding) and b.show and b.description:
                key = b.key_display or \
                    self.KEY_LABELS.get(b.key, b.key.replace("ctrl+", "^"))
                parts.append((key, b.description))
        width = max(10, self.size.width - 2)
        out = Text(no_wrap=False, end="")
        col = 0
        for i, (key, label) in enumerate(parts):
            chunk = len(key) + 1 + len(label) + (2 if col else 0)
            if col and col + chunk > width:
                out.append("\n")
                col = 0
                chunk -= 2
            elif col:
                out.append("  ")
            out.append(key, f"bold {theme.ORANGE}")
            out.append(" " + label, theme.GRAY)
            col += chunk
        return out


class TypingArea(Static):
    """Окно текста: lines_before строк набранного сверху, курсорная строка,
    lines_after строк снизу."""

    engine = None  # type: Engine | None

    def __init__(self, lines_before, lines_after, cursor_style):
        super().__init__()
        self.lines_before = lines_before
        self.lines_after = lines_after
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

        first = cur_line - self.lines_before
        out = Text(no_wrap=True, end="")
        for i in range(first, cur_line + self.lines_after + 1):
            if i != first:
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
    """Полноширинный прогресс-бар книги: │━━━╌ 12.34% ╌╌╌╌│."""

    engine = None  # type: Engine | None

    def render(self):
        if self.engine is None:
            return ""
        pct = self.engine.percent
        width = max(20, self.size.width) - 2  # каёмки по краям
        label = f" {pct:.2f}% "
        start = (width - len(label)) // 2
        filled = round(width * pct / 100)
        out = Text(no_wrap=True, end="")
        out.append("│", theme.DIM)
        for i in range(width):
            if start <= i < start + len(label):
                out.append(label[i - start], f"bold {theme.FG}")
            elif i < filled:
                out.append("━", theme.ORANGE)
            else:
                out.append("╌", theme.DIM)
        out.append("│", theme.DIM)
        return out


class StatusBar(Horizontal):
    def compose(self):
        # type: () -> ComposeResult
        yield Static(id="status-left")
        yield Static(id="status-right")

    def update_status(self, engine, book):
        # type: (Engine, object) -> None
        n = len(book.chapters)
        left = f" {book.title} · Гл. {engine.chapter_idx + 1}/{n}"
        s = engine.stats
        right = (f"{s.cpm_now:.0f} зн/мин · {s.wpm_now:.0f} wpm"
                 f" · {s.accuracy:.0f}% ")
        self.query_one("#status-left", Static).update(left)
        self.query_one("#status-right", Static).update(right)


class TypingScreen(Screen):
    AUTO_FOCUS = None
    BINDINGS = [
        Binding("escape", "menu", "Меню"),
        Binding("ctrl+f", "app.search", "Поиск"),
        Binding("left", "prev_sentence", "←предл", key_display="←"),
        Binding("right", "next_sentence", "предл→", key_display="→"),
        Binding("up", "prev_paragraph", "↑абзац", key_display="↑"),
        Binding("down", "next_paragraph", "абзац↓", key_display="↓"),
        Binding("pageup", "prev_chapter", "глава", key_display="⇞"),
        Binding("pagedown", "next_chapter", "глава", key_display="⇟"),
        Binding("ctrl+b", "app.shelf", "Полка"),
        Binding("ctrl+s", "app.stats", "Статистика"),
        Binding("ctrl+n", "app.random_note", "Заметка"),
    ]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(id="banner")
        cursor = theme.CURSOR_BLOCK if self.app.cfg["cursor"] == "block" \
            else theme.CURSOR_LINE
        yield TypingArea(self.app.cfg["lines_before"],
                         self.app.cfg["lines_after"], cursor)
        yield BookProgress(id="book-progress")
        yield StatusBar(id="status")
        yield WrapFooter()

    def on_mount(self):
        # type: () -> None
        self.query_one(TypingArea).engine = self.app.engine
        self.query_one(BookProgress).engine = self.app.engine
        self.refresh_all()
        self.set_interval(1.0, self.update_status)

    def on_screen_resume(self):
        # type: () -> None
        """Применить настройки, которые могли поменять в диалоге."""
        if self.app.engine is None:  # выход через меню: сессия уже закрыта
            return
        cfg = self.app.cfg
        area = self.query_one(TypingArea)
        area.lines_before = cfg["lines_before"]
        area.lines_after = cfg["lines_after"]
        area.cursor_style = theme.CURSOR_BLOCK if cfg["cursor"] == "block" \
            else theme.CURSOR_LINE
        e = self.app.engine
        e.error_tail_max = cfg["error_tail_max"]
        e.stats.idle_timeout = cfg["idle_timeout"]
        self.refresh_all()

    def action_menu(self):
        # type: () -> None
        self.app.engine.stats.pause()
        self.app.push_screen(MenuScreen())

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
        if result != Result.DONE:
            return
        if self.app.note_mode:
            st = self.app.engine.stats
            self.notify(f"Заметка набрана! {st.chars} знаков · "
                        f"{st.wpm * 5:.0f} зн/мин · точность {st.accuracy:.0f}%"
                        f" · Ctrl+N — следующая", timeout=15)
        elif self.app.engine.book_done:
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
    BINDINGS = [Binding("enter", "open", "Открыть книгу"),
                Binding("escape", "back", "Назад")]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(Text("Библиотека", style=f"bold {theme.YELLOW}",
                          justify="center"), id="banner")
        yield OptionList(id="shelf")
        yield WrapFooter()

    def action_open(self):
        # type: () -> None
        ol = self.query_one(OptionList)
        if ol.option_count:
            ol.action_select()

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
        ol.highlighted = 0  # первый пункт сразу готов к Enter

    def on_option_list_option_selected(self, event):
        # type: (object) -> None
        self.app.open_book(Path(event.option.id))

    def action_back(self):
        # type: () -> None
        if self.app.engine is not None:
            self.app.pop_screen()
        else:
            self.app.exit()


class MenuScreen(ModalScreen):
    BINDINGS = [Binding("escape", "close", "Продолжить")]

    def items(self):
        # type: () -> list[tuple[str, str]]
        app = self.app
        items = [("continue", "Продолжить")]
        if app.cfg["vault_dir"]:
            items.append(("note", "Следующая заметка" if app.note_mode
                          else "Случайная заметка"))
        if app.note_mode and app.last_book_path is not None:
            items.append(("book", f'Вернуться к книге "{app.last_book_title}"'))
        items += [("settings", "Настройки"), ("stats", "Статистика"),
                  ("shelf", "Библиотека"), ("quit", "Выйти")]
        return items

    def compose(self):
        # type: () -> ComposeResult
        with Vertical(id="menu-panel"):
            yield Static(Text("nabor", style=f"bold {theme.YELLOW}",
                              justify="center"), id="menu-title")
            yield OptionList(*[Option(label, id=key)
                               for key, label in self.items()])

    def on_mount(self):
        # type: () -> None
        self.query_one(OptionList).highlighted = 0

    def on_option_list_option_selected(self, event):
        # type: (object) -> None
        self.dismiss()
        action = event.option.id
        if action == "note":
            self.app.open_note()
        elif action == "book":
            self.app.open_book(self.app.last_book_path)
        elif action == "settings":
            self.app.push_screen(SettingsScreen())
        elif action == "stats":
            self.app.push_screen(StatsScreen())
        elif action == "shelf":
            self.app.push_screen(ShelfScreen())
        elif action == "quit":
            self.app.quit_app()

    def action_close(self):
        # type: () -> None
        self.dismiss()


class FormSelect(Select):
    """Select для формы: стрелки ходят по полям, варианты — только по
    Enter/Space (дефолтный Select раскрывается и стрелками — в форме это
    ломает навигацию)."""

    BINDINGS = [
        Binding("down", "app.focus_next", show=False),
        Binding("up", "app.focus_previous", show=False),
    ]


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Назад"),
                Binding("down", "app.focus_next", "след. поле",
                        key_display="↓"),
                Binding("up", "app.focus_previous", "пред. поле",
                        key_display="↑"),
                Binding("ctrl+r", "reset", "Сбросить дефолты")]

    NUM_FIELDS = [
        ("error_tail_max", "Хвост ошибок (0 — ни шагу с ошибкой)", 0, 8),
        ("lines_before", "Строк набранного текста сверху", 0, 8),
        ("lines_after", "Строк будущего текста снизу", 0, 8),
        ("idle_timeout", "Стоп таймера при простое, сек", 1, 60),
    ]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(Text("Настройки", style=f"bold {theme.YELLOW}",
                          justify="center"), id="banner")
        with Vertical(id="settings-form"):
            with Horizontal(classes="settings-row"):
                yield Label("Курсор")
                yield FormSelect([("линия", "line"), ("блок", "block")],
                                 value=self.app.cfg["cursor"],
                                 allow_blank=False, id="set-cursor")
            for key, label, _, _ in self.NUM_FIELDS:
                with Horizontal(classes="settings-row"):
                    yield Label(label)
                    yield Input(value=f"{self.app.cfg[key]:g}",
                                type="integer", id=f"set-{key}")
        yield Static(Text("числа печатаются как есть · сохраняется в "
                          "settings.json (config.toml не трогается)",
                          style=theme.DIM, justify="center"),
                     id="settings-hint")
        yield WrapFooter()

    def on_select_changed(self, event):
        # type: (object) -> None
        self.app.cfg["cursor"] = event.value
        save_ui_settings(self.app.cfg)

    def on_input_changed(self, event):
        # type: (object) -> None
        key = event.input.id.removeprefix("set-")
        field = next(f for f in self.NUM_FIELDS if f[0] == key)
        try:
            val = int(event.value)
        except ValueError:
            return  # пустое/недопечатанное — не применяем
        val = max(field[2], min(val, field[3]))
        self.app.cfg[key] = float(val) if key == "idle_timeout" else val
        save_ui_settings(self.app.cfg)

    def action_reset(self):
        # type: () -> None
        for key in UI_KEYS:
            self.app.cfg[key] = DEFAULTS[key]
        save_ui_settings(self.app.cfg)
        self.query_one("#set-cursor", Select).value = DEFAULTS["cursor"]
        for key, _, _, _ in self.NUM_FIELDS:
            self.query_one(f"#set-{key}", Input).value = f"{DEFAULTS[key]:g}"

    def action_back(self):
        # type: () -> None
        self.app.pop_screen()


class SearchScreen(ModalScreen):
    BINDINGS = [Binding("escape", "close", "Закрыть")]
    MAX_RESULTS = 50

    def compose(self):
        # type: () -> ComposeResult
        with Vertical(id="search-panel"):
            yield Input(placeholder="Поиск по книге…", id="search-input")
            yield OptionList(id="search-results")
            yield Static(Text("↑↓ выбор · Enter — перейти · Esc — закрыть",
                              style=theme.DIM, justify="center"))

    def on_key(self, event):
        # type: (object) -> None
        """Стрелки листают результаты, не покидая поля ввода."""
        if event.key not in ("up", "down"):
            return
        ol = self.query_one("#search-results", OptionList)
        if ol.option_count:
            cur = ol.highlighted or 0
            step = 1 if event.key == "down" else -1
            ol.highlighted = max(0, min(cur + step, ol.option_count - 1))
        event.stop()
        event.prevent_default()

    def on_input_changed(self, event):
        # type: (object) -> None
        ol = self.query_one("#search-results", OptionList)
        ol.clear_options()
        q = event.value.strip().lower()
        if len(q) < 2:
            return
        count = 0
        for ci, chapter in enumerate(self.app.book.chapters):
            low = chapter.text.lower()
            pos = low.find(q)
            while pos != -1 and count < self.MAX_RESULTS:
                snippet = Text.assemble(
                    (f"Гл. {ci + 1:>3}  ", theme.YELLOW),
                    ("…" + chapter.text[max(0, pos - 25):pos].replace("\n", " "),
                     theme.GRAY),
                    (chapter.text[pos:pos + len(q)], f"bold {theme.ORANGE}"),
                    (chapter.text[pos + len(q):pos + len(q) + 35]
                     .replace("\n", " ") + "…", theme.GRAY))
                ol.add_option(Option(snippet, id=f"{ci}|{pos}"))
                count += 1
                pos = low.find(q, pos + len(q))
            if count >= self.MAX_RESULTS:
                break
        if ol.option_count:
            ol.highlighted = 0  # новый ввод — выбор снова на первом

    def on_input_submitted(self, event):
        # type: (object) -> None
        ol = self.query_one("#search-results", OptionList)
        if ol.option_count:
            self._jump(ol.get_option_at_index(ol.highlighted or 0).id)

    def on_option_list_option_selected(self, event):
        # type: (object) -> None
        self._jump(event.option.id)

    def _jump(self, option_id):
        # type: (str) -> None
        ci, pos = map(int, option_id.split("|"))
        self.app.engine.goto(ci, pos)
        self.app.save_position()
        self.dismiss()

    def action_close(self):
        # type: () -> None
        self.dismiss()


class StatsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Назад")]

    def compose(self):
        # type: () -> ComposeResult
        yield Static(Text("Статистика", style=f"bold {theme.YELLOW}",
                          justify="center"), id="banner")
        with VerticalScroll(id="stats-scroll"):
            yield Static(id="stats-body")
        yield WrapFooter()

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
    OptionList > .option-list--option-highlighted {{
        background: {theme.BG2};
        color: {theme.FG};
        text-style: bold;
    }}
    OptionList:focus > .option-list--option-highlighted {{
        background: {theme.BG2};
    }}
    Input {{
        background: {theme.BG1};
    }}
    Input:focus {{
        border: tall {theme.ORANGE};
    }}
    Select:focus > SelectCurrent {{
        border: tall {theme.ORANGE};
    }}
    Input > .input--cursor {{
        background: {theme.ORANGE};
        color: {theme.BG};
    }}
    MenuScreen, SearchScreen {{
        align: center middle;
        background: {theme.BG} 60%;
    }}
    #menu-panel {{
        width: 36;
        height: auto;
        border: round {theme.ORANGE};
        background: {theme.BG};
        padding: 1 2;
    }}
    #menu-panel OptionList, #search-results, #settings-list {{
        background: transparent;
        border: none;
    }}
    #menu-panel OptionList {{
        height: auto;
    }}
    #search-panel {{
        width: 90;
        max-width: 95%;
        height: auto;
        border: round {theme.ORANGE};
        background: {theme.BG};
        padding: 1 2;
    }}
    #search-input {{
        background: {theme.BG1};
        border: none;
        margin-bottom: 1;
    }}
    #search-results {{
        height: auto;
        max-height: 14;
    }}
    #settings-form {{
        height: 1fr;
        margin: 1 6;
    }}
    .settings-row {{
        height: 3;
        margin-bottom: 1;
    }}
    .settings-row Label {{
        width: 42;
        padding: 1 0;
        color: {theme.FG};
    }}
    .settings-row Input {{
        width: 12;
    }}
    .settings-row Select {{
        width: 16;
    }}
    #settings-hint {{
        height: 1;
    }}
    WrapFooter {{
        height: auto;
        background: {theme.BG1};
        padding: 0 1;
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

    def __init__(self, cfg, book_path=None, note=False):
        # type: (dict, Path | None, bool) -> None
        super().__init__()
        self.cfg = cfg
        self._start_path = book_path
        self._start_note = note
        self.book = None
        self.engine = None  # type: Engine | None
        self.note_mode = False       # заметка — разовое упражнение без прогресса
        self.last_book_path = None   # type: Path | None  # куда вернуться из заметки
        self.last_book_title = ""

    def library_books(self):
        # type: () -> list[Path]
        lib = Path(self.cfg["library_dir"])
        books = []
        for pattern in BOOK_GLOBS:
            books.extend(lib.glob(pattern))
        return sorted(set(books))

    def on_mount(self):
        # type: () -> None
        self.set_interval(30.0, self.save_position)
        if self._start_note:
            self.open_note()
            return
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

    def _start_typing(self, book, chapter=0, offset=0):
        # type: (object, int, int) -> None
        self.book = book
        self.engine = Engine(book, chapter, offset,
                             error_tail_max=self.cfg["error_tail_max"],
                             idle_timeout=self.cfg["idle_timeout"])
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self.push_screen(TypingScreen())

    def open_book(self, path):
        # type: (Path) -> None
        self.finish_session()
        book = load_book(path, self.cfg["normalize"],
                         self.cfg["skip_epigraphs"],
                         tuple(self.cfg["skip_paragraphs"]),
                         self.cfg["markdown"])
        chapter, offset, hash_ok = storage.get_position(book)
        self.note_mode = False
        self.last_book_path = path
        self.last_book_title = book.title
        self._start_typing(book, chapter, offset)
        if not hash_ok:
            self.notify("Текст книги изменился — позиция сброшена "
                        "на начало главы", severity="warning", timeout=8)

    def open_note(self):
        # type: () -> None
        """Случайная заметка из Obsidian-хранилища: разовое упражнение —
        прогресс не пишется, на полку не попадает."""
        vault = self.cfg["vault_dir"]
        if not vault:
            self.notify("Хранилище не задано — укажи vault_dir в config.toml",
                        severity="warning", timeout=8)
            return
        besides = self.book.path if self.note_mode and self.book else None
        try:
            book = random_note(vault, tuple(self.cfg["vault_exclude"]),
                               self.cfg["note_min_chars"], self.cfg["normalize"],
                               self.cfg["markdown"],
                               tuple(self.cfg["skip_paragraphs"]), besides)
        except (ValueError, OSError) as exc:
            self.notify(f"Заметку не открыть: {exc}", severity="error",
                        timeout=8)
            return
        self.finish_session()  # книжную позицию сохранит, заметочную — нет
        self.note_mode = True
        self._start_typing(book)

    def save_position(self):
        # type: () -> None
        if self.engine is not None and not self.note_mode:
            storage.save_position(self.book, self.engine.chapter_idx,
                                  self.engine.offset, self.engine.percent)

    def finish_session(self):
        # type: () -> None
        if self.engine is not None:
            self.save_position()
            storage.append_session(
                self.engine.stats.session_record(self.book.title))
            self.engine = None

    def _pause_timer(self):
        # type: () -> None
        if self.engine is not None:
            self.engine.stats.pause()

    def action_shelf(self):
        # type: () -> None
        if not isinstance(self.screen, ShelfScreen):
            self._pause_timer()
            self.push_screen(ShelfScreen())

    def action_stats(self):
        # type: () -> None
        if not isinstance(self.screen, StatsScreen):
            self._pause_timer()
            self.push_screen(StatsScreen())

    def action_random_note(self):
        # type: () -> None
        self.open_note()

    def action_search(self):
        # type: () -> None
        if self.engine is not None and not isinstance(self.screen,
                                                      SearchScreen):
            self._pause_timer()
            self.push_screen(SearchScreen())

    def quit_app(self):
        # type: () -> None
        self.finish_session()
        self.exit()

    async def action_quit(self):
        # type: () -> None
        self.quit_app()
