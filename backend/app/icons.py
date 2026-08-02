"""Render the fastener/hardware icons as 2D SVGs for the visual pickers.

The pickers show the *real* geometry, not hand-drawn lookalikes, so what you click is what
gets printed. This works by `use`-ing the vendored Cullenect.scad (which imports its modules
without executing its top-level output) and projecting the icon module to 2D.

SVG rather than PNG on purpose: 2D export goes through Manifold/CGAL with no OpenGL context,
which a headless container has no way to provide. It also renders in ~40ms and comes out a
few hundred bytes, so a full picker grid is cheap and scales crisply.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from .scad import CACHE_DIR, OPENSCAD, RENDER_TIMEOUT, SCAD_FILE, RenderError, _scad_value

ICON_CACHE = CACHE_DIR / "icons"

# A fastener icon is head-minus-driver, plus shaft and optional security nub — the same
# composition cullenect_label_generate() uses, minus the label body.
FASTENER_TEMPLATE = """use <{scad}>
projection(cut=false) {{
    union() {{
        difference() {{
            cullenect_head(head={head}, flange={flange});
            cullenect_driver(driver={driver});
        }}
        cullenect_shaft(shaft={shaft}, threads={threads});
        {security}
    }}
}}
"""

HARDWARE_TEMPLATE = """use <{scad}>
projection(cut=false) cullenect_hardware({name});
"""

# The driver alone, so the driver row shows the recess shape rather than a screw head that
# barely changes between options.
DRIVER_TEMPLATE = """use <{scad}>
projection(cut=false) cullenect_driver(driver={driver});
"""

# Head WITHOUT the shaft: with the shaft attached, the four head profiles differ only at one
# end and the options read as identical thumbnails.
HEAD_TEMPLATE = """use <{scad}>
projection(cut=false) difference() {{
    cullenect_head(head={head}, flange={flange});
    cullenect_driver(driver={driver});
}}
"""


def _render_svg(source: str, key: str) -> Path:
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    out = ICON_CACHE / f"{key}.svg"
    if out.exists() and out.stat().st_size > 0:
        return out

    tmpdir = Path(tempfile.mkdtemp(prefix="icon-"))
    scad_path = tmpdir / "icon.scad"
    scad_path.write_text(source)
    tmp_out = tmpdir / "icon.svg"
    try:
        proc = subprocess.run(
            [OPENSCAD, "--backend", "Manifold", "-o", str(tmp_out), str(scad_path)],
            capture_output=True, text=True, timeout=RENDER_TIMEOUT,
            env={**os.environ, "HOME": str(tmpdir)},
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError("icon render timed out") from exc
    if proc.returncode != 0 or not tmp_out.exists() or tmp_out.stat().st_size == 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        raise RenderError("icon render failed: " + " | ".join(detail))
    out.write_bytes(tmp_out.read_bytes())
    return out


def _key(prefix: str, parts: dict) -> str:
    blob = prefix + "|" + "|".join(f"{k}={v}" for k, v in sorted(parts.items()))
    return f"{prefix}-" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def fastener_svg(head: str, driver: str, shaft: str, threads: str,
                 flange: bool = False, security: bool = False) -> Path:
    parts = dict(head=head, driver=driver, shaft=shaft, threads=threads,
                 flange=flange, security=security)
    source = FASTENER_TEMPLATE.format(
        scad=SCAD_FILE,
        head=_scad_value(head), driver=_scad_value(driver),
        shaft=_scad_value(shaft), threads=_scad_value(threads),
        flange=_scad_value(flange),
        security=(f"cullenect_driver(driver=\"security\");" if security else ""),
    )
    return _render_svg(source, _key("fastener", parts))


def head_svg(head: str, driver: str = "phillips", flange: bool = False) -> Path:
    return _render_svg(
        HEAD_TEMPLATE.format(scad=SCAD_FILE, head=_scad_value(head),
                             driver=_scad_value(driver), flange=_scad_value(flange)),
        _key("head", {"head": head, "driver": driver, "flange": flange}),
    )


def driver_svg(driver: str) -> Path:
    return _render_svg(
        DRIVER_TEMPLATE.format(scad=SCAD_FILE, driver=_scad_value(driver)),
        _key("driver", {"driver": driver}),
    )


def hardware_svg(name: str) -> Path:
    return _render_svg(
        HARDWARE_TEMPLATE.format(scad=SCAD_FILE, name=_scad_value(name)),
        _key("hardware", {"name": name}),
    )
