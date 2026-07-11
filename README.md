# nabor

A terminal typing trainer that types your books. Point it at an fb2 or txt file and it walks you through the whole thing, keeping your position, your speed and the characters you keep missing. It also types random notes from an Obsidian vault, if you have one.

## Why

Typing drills on random word lists get boring fast. Typing a book you actually want to read does not — you finish a chapter and you have both practised and read it. The trainer stays out of the way: one window of text, the cursor in the middle, the book's progress bar at the bottom, every key it knows listed in the footer.

Built with [Textual](https://textual.textualize.io/); a spiritual rewrite of [retype](https://github.com/plu5/retype) as a TUI.

## Install

Requires Python 3.11+. There is no package on PyPI — clone and install it in place:

```bash
git clone https://github.com/Applemoon/nabor.git
cd nabor
python3 -m venv .venv
.venv/bin/pip install -e .
```

Drop your books into `library/` (`.fb2`, `.fb2.zip`, `.txt`) and run:

```bash
.venv/bin/nabor                  # resume the last book
.venv/bin/nabor library/book.fb2 # open a given one
.venv/bin/nabor --note           # random note from your Obsidian vault
```

The last one needs a vault to draw from — see `vault_dir` below.

## Config

Everything is optional, and it all lives in one file: copy `config.example.toml` to `config.toml`, which documents every key (`vault_dir` and the other keys named below among them). The settings dialog inside the app (`Esc` → Settings) writes the handful of keys it owns to `settings.json` and never touches your `config.toml`.

The UI speaks English or Russian (`language = "en" | "ru"`, or the settings dialog).

Your data sits next to the code: `progress.json` (positions), `stats.jsonl` (sessions), `settings.json`. All three are gitignored, as is `library/`.

## How it types

**Blocking input.** A wrong character lands in a short red *error tail* and the text does not advance until you fix it. Backspace only eats the tail — what you typed correctly stays typed. Set `error_tail_max = 0` and a single mistake blocks you outright.

**What you see is what you type.** Book typography is normalized on load: em dashes become hyphens, «guillemets» become straight quotes, `…` becomes three dots. No hunting for characters your keyboard does not have. The `[normalize]` table decides what maps to what.

**No noise.** Chapter titles are shown as a banner rather than typed, and so are the ads publishers bake into fb2 files (`skip_paragraphs`). Indents are shown but skipped, so typing a code block is not an exercise in holding down the space bar.

**One error per character.** Getting stuck and mashing five wrong keys counts once, not five times.

**Navigation never fakes your speed.** Jumping by sentence, paragraph or chapter — and the full-text search that lands you on a match — moves your position without scoring a thing.

## Statistics

Every session appends a line to `stats.jsonl`: characters, active time (idle pauses do not count), speed and accuracy. The stats screen totals it up for today, the last 7 days and all time, and shows the characters you miss most often — so you learn which key your fingers keep getting wrong.

## Notes from Obsidian

Set `vault_dir` and the app can pull a random note out of your vault as a one-off exercise: no progress is saved, it never lands on the shelf. Markdown is rendered before typing, so you type the prose, the list items and the code — not the `**` and the `[[ ]]`. Frontmatter, images, tables, formulas and emoji are dropped.

## License

[0BSD](LICENSE) — public-domain-equivalent: take it, use it, no strings, not even a copyright notice to carry around.
