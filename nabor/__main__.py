"""CLI: `nabor` resumes the last book; `nabor book.fb2` opens a given one;
`nabor --note` pulls a random note from the Obsidian vault (vault_dir)."""

import argparse
import sys
from pathlib import Path

from nabor.app import NaborApp
from nabor.config import load_config
from nabor.i18n import set_language, t


def main():
    # type: () -> None
    cfg = load_config()
    set_language(cfg["language"])

    parser = argparse.ArgumentParser(prog="nabor",
                                     description=t("cli_description"))
    parser.add_argument("book", nargs="?", type=Path, help=t("cli_book"))
    parser.add_argument("-n", "--note", action="store_true", help=t("cli_note"))
    args = parser.parse_args()

    if args.book is not None and not args.book.exists():
        sys.exit(t("cli_not_found", path=args.book))
    if args.note and not cfg["vault_dir"]:
        sys.exit(t("cli_no_vault"))

    NaborApp(cfg, args.book, note=args.note).run()


if __name__ == "__main__":
    main()
