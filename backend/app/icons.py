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
import re
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

    # Rendered into a private temp dir and copied in at the end, so concurrent requests
    # for the same icon can't collide over the cache file (see scad.render).
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


# --- label thumbnails -------------------------------------------------------------------
#
# A thumbnail can't be produced the way the icons are. `use <>` imports modules but not the
# file's variables, and the label's text IS file-level state (Text1, Text1_Font, …) — an
# imported module always renders the file's default word, not yours. `-D` only reaches the
# top-level scope, which builds the 3D model.
#
# So the thumbnail is derived from the render we already have. In the exported mesh the
# relief occupies its own z band, and the faces in that band ARE the letter and icon
# shapes — so selecting them and flattening to 2D gives the real geometry, for any text,
# with no second rendering path to keep in sync.

BODY_Z = 1.2          # top face of the label body
RELIEF = 0.2          # emboss/deboss depth


def _relief_polygons(mesh_path: Path, surface: str) -> tuple[list, float, float]:
    """Flatten the relief band of a rendered label to 2D polygons."""
    import xml.etree.ElementTree as ET
    import zipfile

    ns = {"c": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    with zipfile.ZipFile(mesh_path) as zf:
        root = ET.fromstring(zf.read("3D/3dmodel.model"))

    verts, tris = [], []
    for v in root.iter(f"{{{ns['c']}}}vertex"):
        verts.append((float(v.get("x")), float(v.get("y")), float(v.get("z"))))
    for t in root.iter(f"{{{ns['c']}}}triangle"):
        tris.append((int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))))
    if not verts:
        return [], 0.0, 0.0

    # Emboss stands above the body; deboss is a recess whose FLOOR carries the shape.
    # Flush shares the body's top face, so there's nothing to separate — fall back to the
    # body alone rather than drawing something misleading.
    if surface == "deboss":
        lo, hi = BODY_Z - RELIEF - 0.01, BODY_Z - RELIEF + 0.01
    elif surface == "emboss":
        lo, hi = BODY_Z + RELIEF - 0.01, BODY_Z + RELIEF + 0.01
    else:
        lo = hi = None

    selected = []
    if lo is not None:
        selected = [(a, b, c) for a, b, c in tris
                    if all(lo <= verts[i][2] <= hi for i in (a, b, c))]

    # Emit OUTLINES, not the raw triangles. A letter is hundreds of triangles; its outline
    # is one loop. Keeping the triangles produced ~250KB per thumbnail, which is hopeless
    # for a list of a few hundred labels — the outlines come in around 3% of that and are
    # crisper, because interior edges stop being drawn.
    edge_count: dict[tuple[int, int], int] = {}
    for a, b, c in selected:
        for u, v in ((a, b), (b, c), (c, a)):
            edge_count[(min(u, v), max(u, v))] = edge_count.get((min(u, v), max(u, v)), 0) + 1
    boundary = [e for e, n in edge_count.items() if n == 1]

    adjacency: dict[int, list[int]] = {}
    for u, v in boundary:
        adjacency.setdefault(u, []).append(v)
        adjacency.setdefault(v, []).append(u)

    loops, seen = [], set()
    for start in adjacency:
        if start in seen:
            continue
        loop, current, previous = [start], start, None
        seen.add(start)
        while True:
            nxt = next((n for n in adjacency.get(current, []) if n != previous and n not in seen),
                       None)
            if nxt is None:
                break
            loop.append(nxt)
            seen.add(nxt)
            previous, current = current, nxt
        if len(loop) >= 3:
            loops.append([(verts[i][0], verts[i][1]) for i in loop])

    max_x = max(v[0] for v in verts)
    max_y = max(v[1] for v in verts)
    return loops, max_x, max_y


def label_thumbnail_svg(label) -> str:
    """An SVG of the label — its body, with the real text and icons on top."""
    from .scad import label_size_mm, render_label

    width, height = label_size_mm(label)
    try:
        polys, _, _ = _relief_polygons(render_label(label, "3mf"), label.surface)
    except RenderError:
        polys = []

    # One path, even-odd filled: counters inside letters (the hole in an 'o', the middle of
    # an 'A') are separate loops and must read as holes rather than filled blobs.
    d = " ".join(
        "M " + " L ".join(f"{x:.2f},{height - y:.2f}" for x, y in loop) + " Z"
        for loop in polys
    )
    shapes = f'<path d="{d}" fill-rule="evenodd"/>' if d else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img">'
        f'<rect x="0.15" y="0.15" width="{width - 0.3}" height="{height - 0.3}" rx="1.2" '
        f'fill="#d4d4d8" stroke="#71717a" stroke-width="0.2"/>'
        f'<g fill="{label.text_color}" stroke="none" shape-rendering="crispEdges">{shapes}</g>'
        f"</svg>"
    )
