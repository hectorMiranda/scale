"""Persistent settings for Minux PowerToys.

A tiny JSON store under the user's config dir. Everything is best-effort: a
missing or corrupt file just yields defaults, and a failed write is swallowed so
the app never dies over a settings problem.
"""

from __future__ import annotations

import json
import os

APP_DIR = "MinuxPowerToys"


def config_path() -> str:
    base = os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_DIR, "settings.json")


def load() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save(data: dict) -> None:
    try:
        p = config_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
