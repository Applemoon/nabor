"""UI strings in English and Russian; the `language` config key picks one.

Only the interface is translated. Book text, the normalization table and the
publisher-ad patterns are data — they stay in the language of the books.
"""

STRINGS = {
    "en": {
        # status bar
        "chapter_short": "Ch.",
        "status_right": "{cpm:.0f} cpm · {wpm:.0f} wpm · {acc:.0f}%",
        # typing screen bindings
        "menu": "Menu",
        "search": "Search",
        "prev_sentence": "←sent",
        "next_sentence": "sent→",
        "prev_paragraph": "↑para",
        "next_paragraph": "para↓",
        "chapter": "chapter",
        "shelf": "Shelf",
        "stats": "Stats",
        "note": "Note",
        # typing screen notifications
        "note_done": "Note typed! {chars} chars · {cpm:.0f} cpm · "
                     "{acc:.0f}% accuracy · Ctrl+N for the next one",
        "book_done": "Book finished! 🎉",
        "hash_changed": "Book text changed — position reset to the start "
                        "of the chapter",
        "no_vault": "No vault configured — set vault_dir in config.toml",
        "note_failed": "Cannot open a note: {error}",
        # shelf
        "library": "Library",
        "open_book": "Open book",
        "back": "Back",
        "empty_shelf": "Shelf is empty — drop fb2/txt files into library/",
        # menu
        "continue": "Continue",
        "random_note": "Random note",
        "next_note": "Next note",
        "back_to_book": 'Back to "{title}"',
        "settings": "Settings",
        "quit": "Quit",
        # settings
        "next_field": "next field",
        "prev_field": "prev. field",
        "reset_defaults": "Reset to defaults",
        "language": "Language",
        "cursor": "Cursor",
        "cursor_line": "line",
        "cursor_block": "block",
        "set_error_tail_max": "Error tail (0 — no step with an error)",
        "set_lines_before": "Lines of typed text above",
        "set_lines_after": "Lines of upcoming text below",
        "set_idle_timeout": "Idle timeout, sec",
        "settings_hint": "typed in as-is · saved to settings.json "
                         "(config.toml is never touched)",
        # search
        "close": "Close",
        "search_placeholder": "Search the book…",
        "search_hint": "↑↓ select · Enter — jump · Esc — close",
        # stats
        "reset_misses": "Reset misses",
        "misses_reset": "Misses reset ({count})",
        "no_misses": "No misses to reset",
        "stats_empty": "Nothing yet — go type something.",
        "col_sessions": "sessions",
        "col_time": "time",
        "col_chars": "chars",
        "col_cpm": "cpm",
        "col_wpm": "wpm",
        "col_accuracy": "acc.",
        "col_when": "when",
        "col_book": "book",
        "col_minutes": "min",
        "minutes": "{n:.0f} min",
        "row_today": "Today",
        "row_week": "7 days",
        "row_all": "All time",
        "char_misses": "Misses by character:  ",
        "none": "none",
        "recent_sessions": "Recent sessions",
        "now": "▸ now",
        # cli
        "cli_description": "TUI typing trainer for books (fb2/txt/md)",
        "cli_book": "book file; without it — the last book you read",
        "cli_note": "random note from the Obsidian vault",
        "cli_not_found": "File not found: {path}",
        "cli_no_vault": "No vault configured: set vault_dir in config.toml",
    },
    "ru": {
        "chapter_short": "Гл.",
        "status_right": "{cpm:.0f} зн/мин · {wpm:.0f} wpm · {acc:.0f}%",
        "menu": "Меню",
        "search": "Поиск",
        "prev_sentence": "←предл",
        "next_sentence": "предл→",
        "prev_paragraph": "↑абзац",
        "next_paragraph": "абзац↓",
        "chapter": "глава",
        "shelf": "Полка",
        "stats": "Статистика",
        "note": "Заметка",
        "note_done": "Заметка набрана! {chars} знаков · {cpm:.0f} зн/мин · "
                     "точность {acc:.0f}% · Ctrl+N — следующая",
        "book_done": "Книга закончена! 🎉",
        "hash_changed": "Текст книги изменился — позиция сброшена "
                        "на начало главы",
        "no_vault": "Хранилище не задано — укажи vault_dir в config.toml",
        "note_failed": "Заметку не открыть: {error}",
        "library": "Библиотека",
        "open_book": "Открыть книгу",
        "back": "Назад",
        "empty_shelf": "Библиотека пуста — положи fb2/txt в library/",
        "continue": "Продолжить",
        "random_note": "Случайная заметка",
        "next_note": "Следующая заметка",
        "back_to_book": 'Вернуться к книге "{title}"',
        "settings": "Настройки",
        "quit": "Выйти",
        "next_field": "след. поле",
        "prev_field": "пред. поле",
        "reset_defaults": "Сбросить дефолты",
        "language": "Язык",
        "cursor": "Курсор",
        "cursor_line": "линия",
        "cursor_block": "блок",
        "set_error_tail_max": "Хвост ошибок (0 — ни шагу с ошибкой)",
        "set_lines_before": "Строк набранного текста сверху",
        "set_lines_after": "Строк будущего текста снизу",
        "set_idle_timeout": "Стоп таймера при простое, сек",
        "settings_hint": "числа печатаются как есть · сохраняется в "
                         "settings.json (config.toml не трогается)",
        "close": "Закрыть",
        "search_placeholder": "Поиск по книге…",
        "search_hint": "↑↓ выбор · Enter — перейти · Esc — закрыть",
        "reset_misses": "Сбросить промахи",
        "misses_reset": "Промахи сброшены ({count})",
        "no_misses": "Промахов и так нет",
        "stats_empty": "Пока пусто — напечатай что-нибудь.",
        "col_sessions": "сессий",
        "col_time": "время",
        "col_chars": "знаков",
        "col_cpm": "зн/мин",
        "col_wpm": "wpm",
        "col_accuracy": "точн.",
        "col_when": "когда",
        "col_book": "книга",
        "col_minutes": "мин",
        "minutes": "{n:.0f} мин",
        "row_today": "Сегодня",
        "row_week": "7 дней",
        "row_all": "Всё время",
        "char_misses": "Промахи по символам:  ",
        "none": "нет",
        "recent_sessions": "Последние сессии",
        "now": "▸ сейчас",
        "cli_description": "TUI-тренажёр печати по книгам (fb2/txt/md)",
        "cli_book": "файл книги; без аргумента — последняя книга",
        "cli_note": "случайная заметка из Obsidian-хранилища",
        "cli_not_found": "Файл не найден: {path}",
        "cli_no_vault": "Хранилище не задано: укажи vault_dir в config.toml",
    },
}

LANGUAGES = tuple(STRINGS)

_lang = "en"


def set_language(lang):
    # type: (str) -> None
    global _lang
    _lang = lang if lang in STRINGS else "en"


def t(key, **kw):
    # type: (str, object) -> str
    """UI string in the current language; falls back to English."""
    text = STRINGS[_lang].get(key) or STRINGS["en"][key]
    return text.format(**kw) if kw else text
