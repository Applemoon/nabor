"""Конфиг: дефолты в коде ← config.toml (правится руками, приложение его
никогда не пишет) ← settings.json (пишется диалогом настроек в UI)."""

import json
import tomllib
from pathlib import Path

from nabor.normalize import DEFAULT_TABLE

ROOT = Path(__file__).resolve().parent.parent  # корень репо = папка данных
SETTINGS_PATH = ROOT / "settings.json"

DEFAULTS = {
    "library_dir": str(ROOT / "library"),
    "lines_before": 2,        # строк набранного текста над курсорной строкой
    "lines_after": 2,         # строк будущего текста под курсорной строкой
    "error_tail_max": 4,      # хвост ошибок; 0 = жёсткая блокировка
    "idle_timeout": 5.0,      # стоп таймера после стольких секунд простоя
    "cursor": "line",         # "line" (подчёркивание) или "block"
}

# ключи, которые правит диалог настроек в UI (уходят в settings.json)
UI_KEYS = ("cursor", "error_tail_max", "lines_before", "lines_after",
           "idle_timeout")


def load_config(path=None):
    # type: (Path | None) -> dict
    cfg = dict(DEFAULTS)
    cfg["normalize"] = dict(DEFAULT_TABLE)
    path = path or ROOT / "config.toml"
    if path.exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)
        # таблица нормализации берётся целиком, не мержится (как rdict в retype)
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
