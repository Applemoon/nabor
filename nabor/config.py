"""Config layers: defaults in code ← config.toml (hand-edited, never written
by the app) ← settings.json (written by the in-app settings dialog)."""

import json
import tomllib
from pathlib import Path

from nabor.normalize import DEFAULT_TABLE

ROOT = Path(__file__).resolve().parent.parent  # repo root doubles as data dir
SETTINGS_PATH = ROOT / "settings.json"

# Publisher ads: promo paragraphs baked into fb2 files by the sites that
# distribute them (litres, royallib, hpmor.ru). They share no reliable marker,
# so we match known wordings; add your own patterns in config.toml. The
# defaults are Russian because that is where such ads come from.
DEFAULT_SKIP_PARAGRAPHS = [
    r"^Мы рады представить вам электронную версию",
    r"^Опубликовано на .*https?://",
    r"^Текст предоставлен правообладател",
    r"купив полную легальную версию",
    r"Эта книга была куплена в интернет-магазине",
    r"^Данный файл (был )?(скачан|получен)",
    r"заходите к нам на https?://",
]

DEFAULTS = {
    "language": "en",         # UI language: "en" or "ru"
    "library_dir": str(ROOT / "library"),
    "lines_before": 2,        # lines of typed text above the cursor line
    "lines_after": 2,         # lines of upcoming text below the cursor line
    "error_tail_max": 4,      # error tail length; 0 = hard block on a mistake
    "idle_timeout": 5.0,      # speed timer stops after this many idle seconds
    "cursor": "line",         # "line" (underline) or "block"
    "skip_epigraphs": False,  # fb2 epigraphs are typed (in HPMOR they are jokes)
    "skip_paragraphs": DEFAULT_SKIP_PARAGRAPHS,  # regexes of publisher ads
    "vault_dir": "",          # Obsidian vault; empty = note mode is off
    "vault_exclude": [],      # top-level folders/files kept out of the pool
    "note_min_chars": 300,    # shorter notes are no exercise — pull the next one
    "markdown": "rendered",   # "rendered" (markup stripped) or "raw" (source)
}

# keys the in-app settings dialog owns (they go to settings.json)
UI_KEYS = ("language", "cursor", "error_tail_max", "lines_before",
           "lines_after", "idle_timeout")


def load_config(path=None):
    # type: (Path | None) -> dict
    cfg = dict(DEFAULTS)
    cfg["normalize"] = dict(DEFAULT_TABLE)
    path = path or ROOT / "config.toml"
    if path.exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)
        # the normalization table replaces the built-in one wholesale, no merge
        table = user.pop("normalize", None)
        if table is not None:
            cfg["normalize"] = table
        cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    if SETTINGS_PATH.exists():
        ui = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in ui.items() if k in UI_KEYS})
    return cfg


def save_ui_settings(cfg):
    # type: (dict) -> None
    SETTINGS_PATH.write_text(
        json.dumps({k: cfg[k] for k in UI_KEYS}, ensure_ascii=False, indent=2),
        encoding="utf-8")
