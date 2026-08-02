"""Persistent label library — a JSON file on the container's /data volume.

Deliberately a plain file, not a database: the library is the artifact Dave
actually cares about keeping, and a file can be downloaded, diffed, committed
and restored without any export tooling.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Label, Library

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
LIBRARY_PATH = DATA_DIR / "labels.json"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(lib: Library) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LIBRARY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib.model_dump(), indent=2))
    tmp.replace(LIBRARY_PATH)          # atomic — never leave a half-written library


def load() -> Library:
    if not LIBRARY_PATH.exists():
        # Persist the seed set immediately — regenerating it per request would
        # hand out fresh ids each time and every save/delete would 404.
        seeded = Library(labels=list(seed_labels()))
        _write(seeded)
        return seeded
    try:
        return Library.model_validate(json.loads(LIBRARY_PATH.read_text()))
    except Exception:
        # Never lose the user's data to a parse error — park it and start clean.
        backup = LIBRARY_PATH.with_name(f"labels.corrupt.{int(datetime.now().timestamp())}.json")
        LIBRARY_PATH.replace(backup)
        return Library(labels=[])


def save(lib: Library) -> Library:
    with _lock:
        _write(lib)
    return lib


def list_labels() -> list[Label]:
    return load().labels


def get(label_id: str) -> Label | None:
    return next((l for l in load().labels if l.id == label_id), None)


def add(label: Label) -> Label:
    with _lock:
        lib = load()
        label.id = label.id or uuid.uuid4().hex[:12]
        label.created_at = label.created_at or _now()
        label.updated_at = _now()
        lib.labels.append(label)
        _write(lib)
    return label


def add_many(labels: list[Label]) -> list[Label]:
    """Append a batch in one write — a 40-line paste shouldn't be 40 file rewrites,
    and a partial batch on a crash would be worse than none."""
    with _lock:
        lib = load()
        created = []
        for label in labels:
            label.id = label.id or uuid.uuid4().hex[:12]
            label.created_at = label.created_at or _now()
            label.updated_at = _now()
            lib.labels.append(label)
            created.append(label)
        _write(lib)
    return created


def update(label_id: str, label: Label) -> Label | None:
    with _lock:
        lib = load()
        for i, existing in enumerate(lib.labels):
            if existing.id == label_id:
                label.id = label_id
                label.created_at = existing.created_at
                label.updated_at = _now()
                lib.labels[i] = label
                _write(lib)
                return label
    return None


def delete(label_id: str) -> bool:
    with _lock:
        lib = load()
        remaining = [l for l in lib.labels if l.id != label_id]
        if len(remaining) == len(lib.labels):
            return False
        lib.labels = remaining
        _write(lib)
    return True


def reorder(order: list[str]) -> list[Label]:
    with _lock:
        lib = load()
        by_id = {l.id: l for l in lib.labels}
        ordered = [by_id[i] for i in order if i in by_id]
        ordered += [l for l in lib.labels if l.id not in set(order)]  # keep strays
        lib.labels = ordered
        _write(lib)
        return ordered


def replace_all(labels: list[Label]) -> list[Label]:
    """Import — every label gets an id and timestamps."""
    with _lock:
        for l in labels:
            l.id = l.id or uuid.uuid4().hex[:12]
            l.created_at = l.created_at or _now()
            l.updated_at = _now()
        lib = Library(labels=labels)
        _write(lib)
        return labels


def seed_labels():
    """A small starter set so a fresh instance isn't an empty screen."""
    from .models import Fastener, TextBlock

    def mk(name, t1, t2="", **kw):
        return Label(
            id=uuid.uuid4().hex[:12], name=name, created_at=_now(), updated_at=_now(),
            text1=TextBlock(text=t1), text2=TextBlock(text=t2, align="right", size=6), **kw,
        )

    yield mk("M3 socket cap 12mm", "M3 x 12", fastener=Fastener(show=True, head="socket", driver="hex"))
    yield mk("M4 socket cap 20mm", "M4 x 20", fastener=Fastener(show=True, head="socket", driver="hex"))
    yield mk("M3 nylon lock nuts", "M3", hardware="nut_nylon")
    yield mk("M4 washers", "M4", hardware="washer")
    yield mk("M3 heat-set inserts", "M3", hardware="threaded_insert")
    yield mk("Wire ferrules", "Ferrules", "22-16", width_u=2)
