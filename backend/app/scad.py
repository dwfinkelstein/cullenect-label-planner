"""Drive OpenSCAD headlessly to turn a Label into a colored 3MF / STL.

Two things make this fast enough to render on demand instead of batch-queueing:
  * the Manifold backend (~0.5s per label; the old CGAL backend takes ~2 minutes)
  * a content-addressed cache — the same parameters never render twice.

Colored 3MF needs a recent OpenSCAD (2025+); `export-3mf/color-mode` does not
exist on 2021.01. See Dockerfile for the pinned nightly.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .models import Label

log = logging.getLogger(__name__)

OPENSCAD = os.environ.get("OPENSCAD_BIN", "openscad")
SCAD_FILE = Path(os.environ.get("SCAD_FILE", Path(__file__).parent.parent / "scad" / "Cullenect.scad"))
CACHE_DIR = Path(os.environ.get("RENDER_CACHE", "/data/render-cache"))
RENDER_TIMEOUT = int(os.environ.get("RENDER_TIMEOUT", "120"))

SURFACE_CODE = {"emboss": 0, "deboss": 1, "flush": 2}

# Select_Output values in Cullenect.scad
OUTPUT_LABEL = 0
ACCESSORIES = {
    "label-spacer": 1,
    "socket-test-fit": 10,
    "socket-negative": 11,
    "vertical-socket-test-fit": 20,
    "vertical-socket-negative": 21,
}


class RenderError(RuntimeError):
    pass


def _scad_value(v) -> str:
    """Serialize a Python value as an OpenSCAD literal for -D."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_scad_value(x) for x in v) + "]"
    # json.dumps gives us correct quoting/escaping for OpenSCAD string literals
    return json.dumps(str(v))


def label_defines(label: Label) -> dict[str, object]:
    """Map a Label onto Cullenect.scad's customizer variables."""
    t1, t2, f = label.text1, label.text2, label.fastener
    return {
        "Select_Output": OUTPUT_LABEL,
        "label_width": label.width_u,
        "backward_compatible": label.backward_compatible,
        "label_surface": SURFACE_CODE[label.surface],
        "Text_Color": label.text_color,
        "Text1": t1.text,
        "Text1_Align": t1.align,
        "Text1_Font_Size": t1.size,
        "Text1_Font": t1.font,
        "Text1_Font_Style": t1.style,
        "Text1_XY": [t1.dx, t1.dy],
        "Text2": t2.text,
        "Text2_Align": t2.align,
        "Text2_Font_Size": t2.size,
        "Text2_Font": t2.font,
        "Text2_Font_Style": t2.style,
        "Text2_XY": [t2.dx, t2.dy],
        "Show_Fastener": f.show,
        "Fastener_Head": f.head,
        "Fastener_Shaft": f.shaft,
        "Fastener_Threads": f.threads,
        "Fastener_Driver": f.driver,
        "Fastener_Head_Flange": f.flange,
        "Fastener_Driver_Security": f.security,
        "Select_Hardware": label.hardware,
    }


def label_size_mm(label: Label) -> tuple[float, float]:
    """Footprint of the rendered label — used to lay out a plate."""
    return (label.width_u * 42 - 6, 11.0)


def _cache_key(defines: dict, fmt: str) -> str:
    blob = json.dumps(defines, sort_keys=True) + f"|{fmt}|{SCAD_FILE.stat().st_mtime_ns}"
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def render(defines: dict[str, object], fmt: str = "3mf") -> Path:
    """Render the .scad with the given -D overrides. Returns a cached file path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{_cache_key(defines, fmt)}.{fmt}"
    if out.exists() and out.stat().st_size > 0:
        return out

    cmd = [OPENSCAD, "--backend", "Manifold", "-o", str(out)]
    if fmt == "3mf":
        cmd += [
            "-O", "export-3mf/color-mode=model",
            "-O", "export-3mf/material-type=color",
            "-O", "export-3mf/decimal-precision=4",
            "-O", "export-3mf/add-meta-data=false",
        ]
    for k, v in defines.items():
        cmd += ["-D", f"{k}={_scad_value(v)}"]
    cmd.append(str(SCAD_FILE))

    tmp_home = tempfile.mkdtemp(prefix="oscad-")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=RENDER_TIMEOUT,
            env={**os.environ, "HOME": tmp_home},
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"OpenSCAD timed out after {RENDER_TIMEOUT}s") from exc

    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        raise RenderError("OpenSCAD failed: " + " | ".join(detail))

    log.info("rendered %s (%d bytes)", out.name, out.stat().st_size)
    return out


def render_label(label: Label, fmt: str = "3mf") -> Path:
    return render(label_defines(label), fmt)


def render_accessory(kind: str, width_u: float = 1, fmt: str = "3mf") -> Path:
    if kind not in ACCESSORIES:
        raise RenderError(f"unknown accessory {kind!r}")
    return render(
        {"Select_Output": ACCESSORIES[kind], "label_width": width_u, "backward_compatible": True},
        fmt,
    )


def openscad_version() -> str:
    try:
        proc = subprocess.run([OPENSCAD, "--version"], capture_output=True, text=True, timeout=30)
        return (proc.stdout or proc.stderr).strip().splitlines()[0]
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def missing_fonts(families: list[str]) -> list[str]:
    """Families fontconfig would silently substitute — a wrong font changes the
    printed label, so the UI surfaces this rather than letting it pass."""
    missing = []
    for family in families:
        try:
            proc = subprocess.run(
                ["fc-match", "-f", "%{family}", family],
                capture_output=True, text=True, timeout=10,
            )
            # fc-match always returns *something*; the substitute is the tell.
            # Compare the whole family name, so "Open Sans" standing in for
            # "Open Sans Condensed" is correctly reported as missing.
            norm = lambda s: "".join(s.lower().split())
            resolved = {norm(f) for f in (proc.stdout or "").split(",")}
            if norm(family) not in resolved:
                missing.append(family)
        except Exception:
            return []          # no fontconfig binary — don't cry wolf
    return missing


def supports_color_3mf() -> bool:
    """Colored 3MF export only exists on newer OpenSCAD — surface it in /api/health."""
    try:
        proc = subprocess.run([OPENSCAD, "--help-export"], capture_output=True, text=True, timeout=30)
        return "export-3mf" in (proc.stdout + proc.stderr)
    except Exception:
        return False
