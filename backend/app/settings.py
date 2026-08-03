"""Printer-side settings, kept separately from the label library.

Plate size and gap describe your PRINTER, not your labels — so they don't belong in
labels.json. Keeping them apart means the library stays a clean portable artifact: you can
hand someone your label list without also handing them your bed size.
"""
from __future__ import annotations

import json
import threading

from pydantic import BaseModel, Field

from .store import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"
_lock = threading.Lock()


class Settings(BaseModel):
    plate_x: float = Field(250, gt=0, le=2000)
    plate_y: float = Field(250, gt=0, le=2000)
    gap: float = Field(3, ge=0, le=50)


def load() -> Settings:
    if not SETTINGS_PATH.exists():
        return Settings()
    try:
        return Settings.model_validate(json.loads(SETTINGS_PATH.read_text()))
    except Exception:
        # Never let a bad settings file stop the app starting — the defaults are fine.
        return Settings()


def save(settings: Settings) -> Settings:
    with _lock:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(settings.model_dump(), indent=2))
        tmp.replace(SETTINGS_PATH)      # atomic, as with the library
    return settings
