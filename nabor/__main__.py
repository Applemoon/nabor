"""CLI: `nabor` — авторезюм последней книги; `nabor книга.fb2` — конкретная."""

import argparse
import sys
from pathlib import Path

from nabor.app import NaborApp
from nabor.config import load_config


def main():
    # type: () -> None
    parser = argparse.ArgumentParser(
        prog="nabor", description="TUI-тренажёр печати по книгам (fb2/txt)")
    parser.add_argument("book", nargs="?", type=Path,
                        help="файл книги; без аргумента — последняя книга")
    args = parser.parse_args()

    if args.book is not None and not args.book.exists():
        sys.exit(f"Файл не найден: {args.book}")

    cfg = load_config()
    NaborApp(cfg, args.book).run()


if __name__ == "__main__":
    main()
