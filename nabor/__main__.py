"""CLI: `nabor` — авторезюм последней книги; `nabor книга.fb2` — конкретная;
`nabor --note` — случайная заметка из Obsidian-хранилища (vault_dir)."""

import argparse
import sys
from pathlib import Path

from nabor.app import NaborApp
from nabor.config import load_config


def main():
    # type: () -> None
    parser = argparse.ArgumentParser(
        prog="nabor", description="TUI-тренажёр печати по книгам (fb2/txt/md)")
    parser.add_argument("book", nargs="?", type=Path,
                        help="файл книги; без аргумента — последняя книга")
    parser.add_argument("-n", "--note", action="store_true",
                        help="случайная заметка из Obsidian-хранилища")
    args = parser.parse_args()

    if args.book is not None and not args.book.exists():
        sys.exit(f"Файл не найден: {args.book}")

    cfg = load_config()
    if args.note and not cfg["vault_dir"]:
        sys.exit("Хранилище не задано: укажи vault_dir в config.toml")
    NaborApp(cfg, args.book, note=args.note).run()


if __name__ == "__main__":
    main()
