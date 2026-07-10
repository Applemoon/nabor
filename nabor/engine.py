"""Ядро набора: позиция, блокирующий ввод с хвостом ошибок, навигация,
статистика. Без Textual — чистая логика."""

import re
import time
from collections import Counter, deque
from enum import Enum

_SENTENCE_END = re.compile(r"[.!?]+[\")']*\s")


class Result(Enum):
    OK = 1        # верный символ, позиция сдвинулась
    MISTAKE = 2   # неверный, лёг в хвост
    BLOCKED = 3   # хвост полон, ввод не принят
    DONE = 4      # верный символ, глава закончена


class Stats:
    """Статистика сессии. Активное время: паузы длиннее idle_timeout
    не считаются."""

    def __init__(self, idle_timeout=5.0, clock=time.monotonic):
        self.idle_timeout = idle_timeout
        self._clock = clock
        self._last_event = None  # type: float | None
        self.active_sec = 0.0
        self.chars = 0       # верно набранные
        self.errors = 0
        self.char_errors = Counter()  # type: Counter[str]  # ожидаемый символ → промахи
        self._recent = deque()  # type: deque[float]  # времена верных символов (для живого WPM)

    def _tick(self):
        # type: () -> float
        now = self._clock()
        if self._last_event is not None:
            dt = now - self._last_event
            if dt <= self.idle_timeout:
                self.active_sec += dt
        self._last_event = now
        return now

    def hit(self):
        # type: () -> None
        now = self._tick()
        self.chars += 1
        self._recent.append(now)

    def miss(self, expected):
        # type: (str) -> None
        self._tick()
        self.errors += 1
        self.char_errors[expected] += 1

    @property
    def wpm(self):
        # type: () -> float
        """Средний WPM по активному времени сессии (слово = 5 символов)."""
        if self.active_sec < 1:
            return 0.0
        return self.chars / 5 / (self.active_sec / 60)

    @property
    def wpm_now(self):
        # type: () -> float
        """Скользящий WPM за последнюю минуту."""
        now = self._clock()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        if not self._recent:
            return 0.0
        span = max(now - self._recent[0], 5.0)
        return len(self._recent) / 5 / (span / 60)

    @property
    def accuracy(self):
        # type: () -> float
        total = self.chars + self.errors
        return 100.0 if total == 0 else self.chars / total * 100

    def session_record(self, book_title):
        # type: (str) -> dict | None
        if self.chars == 0:
            return None
        return {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "book": book_title,
            "active_sec": round(self.active_sec, 1),
            "chars": self.chars,
            "words": round(self.chars / 5),
            "errors": self.errors,
            "wpm": round(self.wpm, 1),
            "accuracy": round(self.accuracy, 1),
            "char_errors": dict(self.char_errors),
        }


class Engine:
    def __init__(self, book, chapter=0, offset=0,
                 error_tail_max=4, idle_timeout=5.0, clock=time.monotonic):
        self.book = book
        self.chapter_idx = min(chapter, len(book.chapters) - 1)
        self.offset = offset
        self.tail = []  # type: list[str]  # ошибочно набранные символы
        self.error_tail_max = error_tail_max
        self.stats = Stats(idle_timeout, clock)
        self._chapter_lens = [len(c.text) + 1 for c in book.chapters]
        self._total = sum(self._chapter_lens)
        self._load_chapter()

    # --- текущая глава ---------------------------------------------------

    def _load_chapter(self):
        # type: () -> None
        self.text = self.book.chapters[self.chapter_idx].text
        self.offset = min(self.offset, len(self.text))
        self.tail.clear()
        # границы предложений и абзацев (индексы начал)
        starts = {0}
        for m in _SENTENCE_END.finditer(self.text):
            starts.add(m.end())
        for i, ch in enumerate(self.text):
            if ch == "\n":
                starts.add(i + 1)
        self.sentence_starts = sorted(starts)
        self.paragraph_starts = [0] + [i + 1 for i, c in enumerate(self.text)
                                       if c == "\n"]

    @property
    def chapter(self):
        return self.book.chapters[self.chapter_idx]

    @property
    def expected(self):
        # type: () -> str | None
        return self.text[self.offset] if self.offset < len(self.text) else None

    @property
    def chapter_done(self):
        # type: () -> bool
        return self.offset >= len(self.text)

    @property
    def book_done(self):
        # type: () -> bool
        return self.chapter_done and \
            self.chapter_idx == len(self.book.chapters) - 1

    @property
    def percent(self):
        # type: () -> float
        done = sum(self._chapter_lens[:self.chapter_idx]) + self.offset
        return done / self._total * 100

    # --- ввод -------------------------------------------------------------

    def type_char(self, ch):
        # type: (str) -> Result
        expected = self.expected
        if expected is None:
            return Result.BLOCKED
        if self.tail:
            if len(self.tail) >= self.error_tail_max:
                return Result.BLOCKED
            self.tail.append(ch)
            self.stats.miss(expected)
            return Result.MISTAKE
        if ch == expected:
            self.offset += 1
            self.stats.hit()
            return Result.DONE if self.chapter_done else Result.OK
        self.tail.append(ch)
        self.stats.miss(expected)
        return Result.MISTAKE

    def backspace(self):
        # type: () -> bool
        """Стирает только хвост ошибок; верно набранное не трогаем."""
        if self.tail:
            self.tail.pop()
            return True
        return False

    # --- навигация (позицию двигает, статистику не начисляет) -------------

    def _goto(self, offset):
        # type: (int) -> None
        self.offset = max(0, min(offset, len(self.text)))
        self.tail.clear()

    def next_sentence(self):
        # type: () -> None
        nxt = [s for s in self.sentence_starts if s > self.offset]
        if nxt:
            self._goto(nxt[0])
        elif not self.book_done:
            self.next_chapter()

    def prev_sentence(self):
        # type: () -> None
        prev = [s for s in self.sentence_starts if s < self.offset]
        if prev:
            self._goto(prev[-1])
        elif self.chapter_idx > 0:
            self.prev_chapter(to_end=True)

    def next_paragraph(self):
        # type: () -> None
        nxt = [s for s in self.paragraph_starts if s > self.offset]
        if nxt:
            self._goto(nxt[0])
        elif not self.book_done:
            self.next_chapter()

    def prev_paragraph(self):
        # type: () -> None
        prev = [s for s in self.paragraph_starts if s < self.offset]
        if prev:
            self._goto(prev[-1])
        elif self.chapter_idx > 0:
            self.prev_chapter(to_end=True)

    def next_chapter(self):
        # type: () -> bool
        if self.chapter_idx + 1 >= len(self.book.chapters):
            return False
        self.chapter_idx += 1
        self.offset = 0
        self._load_chapter()
        return True

    def prev_chapter(self, to_end=False):
        # type: (bool) -> bool
        if self.chapter_idx == 0:
            return False
        self.chapter_idx -= 1
        self.offset = 0
        self._load_chapter()
        if to_end and self.paragraph_starts:
            self._goto(self.paragraph_starts[-1])
        return True
