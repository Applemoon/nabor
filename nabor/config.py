"""Конфиг: дефолты в коде, config.toml перекрывает. Приложение конфиг
никогда не пишет — только читает при старте."""

import tomllib
from pathlib import Path

from nabor.normalize import DEFAULT_TABLE

ROOT = Path(__file__).resolve().parent.parent  # корень репо = папка данных

DEFAULTS = {
    "library_dir": str(ROOT / "library"),
    "window_lines": 5,        # строк текста на экране (3–5)
    "error_tail_max": 4,      # длина красного хвоста ошибок
    "idle_timeout": 5.0,      # секунд простоя до автопаузы
    "cursor": "line",         # "line" (подчёркивание) или "block"
}


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
    return cfg
