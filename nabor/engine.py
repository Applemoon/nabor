"""Typing core: position, blocking input with an error tail, navigation,
statistics. No Textual here — plain logic."""

import re
import time
from collections import Counter, deque
from enum import Enum

_SENTENCE_END = re.compile(r"[.!?]+[\")']*\s")


class Result(Enum):
    OK = 1        # correct character, position moved on
    MISTAKE = 2   # wrong character, landed in the tail
    BLOCKED = 3   # tail is full, input rejected
    DONE = 4      # correct character, chapter finished


class Stats:
    """Session statistics. Active time: pauses longer than idle_timeout do not
    count."""

    def __init__(self, idle_timeout=5.0, clock=time.monotonic):
        self.idle_timeout = idle_timeout
        self._clock = clock
        self._last_event = None  # type: float | None
        self.active_sec = 0.0
        self.chars = 0       # correctly typed
        self.errors = 0
        self.char_errors = Counter()  # type: Counter[str]  # expected char → misses
        self._recent = deque()  # type: deque[float]  # times of hits, for live WPM

    def pause(self):
        # type: () -> None
        """Explicit pause (a modal or the menu is open): the gap until the next
        keypress will not count, however short it turns out to be."""
        self._last_event = None

    def touch(self):
        # type: () -> None
        """A keypress that counts neither as a hit nor as an error (another
        miss on the same character), but typing time keeps running."""
        self._tick()

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
        """Average WPM over the session's active time (a word = 5 chars)."""
        if self.active_sec < 1:
            return 0.0
        return self.chars / 5 / (self.active_sec / 60)

    @property
    def cpm_now(self):
        # type: () -> float
        """Rolling characters per minute over the last minute."""
        now = self._clock()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        if not self._recent:
            return 0.0
        span = max(now - self._recent[0], 5.0)
        return len(self._recent) / (span / 60)

    @property
    def wpm_now(self):
        # type: () -> float
        """Rolling WPM over the last minute (a word = 5 chars)."""
        return self.cpm_now / 5

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
        self.tail = []  # type: list[str]  # characters typed wrong
        self._missed = False  # the current character already counted as a miss
        self.error_tail_max = error_tail_max
        self.stats = Stats(idle_timeout, clock)
        self._chapter_lens = [len(c.text) + 1 for c in book.chapters]
        self._total = sum(self._chapter_lens)
        self._load_chapter()

    # --- current chapter --------------------------------------------------

    def _skip_indent(self, i):
        # type: (int) -> int
        """Leading spaces of a line (indent of code and nested lists) are shown
        but not typed: a position inside the indent winds on to the first
        character."""
        line_start = self.text.rfind("\n", 0, i) + 1
        j = line_start
        while j < len(self.text) and self.text[j] == " ":
            j += 1
        return j if i <= j else i

    def _load_chapter(self):
        # type: () -> None
        self.text = self.book.chapters[self.chapter_idx].text
        self.offset = self._skip_indent(min(self.offset, len(self.text)))
        self.tail.clear()
        self._missed = False
        # sentence and paragraph boundaries (start indices, indent already
        # skipped — otherwise prev_paragraph would stick: jump to the line
        # start → skip the indent → same position again)
        starts = {0}
        for m in _SENTENCE_END.finditer(self.text):
            starts.add(m.end())
        for i, ch in enumerate(self.text):
            if ch == "\n":
                starts.add(i + 1)
        self.sentence_starts = sorted({self._skip_indent(s) for s in starts})
        self.paragraph_starts = sorted(
            {self._skip_indent(i + 1) for i, c in enumerate(self.text)
             if c == "\n"} | {self._skip_indent(0)})

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

    # --- input ------------------------------------------------------------

    def type_char(self, ch):
        # type: (str) -> Result
        expected = self.expected
        if expected is None:
            return Result.BLOCKED
        if not self.tail and ch == expected:
            self.offset += 1
            if ch == "\n":  # new line — the indent is skipped, not typed
                self.offset = self._skip_indent(self.offset)
            self._missed = False
            self.stats.hit()
            return Result.DONE if self.chapter_done else Result.OK
        # getting stuck on a character = one error, no matter how many wrong
        # keys are pressed before it is finally typed right
        if self._missed:
            self.stats.touch()
        else:
            self.stats.miss(expected)
            self._missed = True
        if len(self.tail) >= self.error_tail_max:
            return Result.BLOCKED  # tail is full (or switched off with a zero)
        self.tail.append(ch)
        return Result.MISTAKE

    def backspace(self):
        # type: () -> bool
        """Erases the error tail only; correctly typed text stays."""
        if self.tail:
            self.tail.pop()
            return True
        return False

    # --- navigation (moves the position, never scores statistics) ----------

    def _goto(self, offset):
        # type: (int) -> None
        self.offset = self._skip_indent(max(0, min(offset, len(self.text))))
        self.tail.clear()
        self._missed = False

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

    def goto(self, chapter_idx, offset=0):
        # type: (int, int) -> None
        """Jump into a chapter, to the start of the sentence holding offset."""
        self.chapter_idx = max(0, min(chapter_idx, len(self.book.chapters) - 1))
        self.offset = 0
        self._load_chapter()
        starts = [s for s in self.sentence_starts if s <= offset]
        self._goto(starts[-1] if starts else 0)

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
