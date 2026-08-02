"""Combine per-label 3MF renders into one build-plate 3MF, colors intact.

OpenSCAD can only render one parameter set per invocation (the customizer values
are file-level globals), so a plate is assembled here instead: each distinct label
is rendered once, then referenced as a 3MF object with one <item> per copy. That
keeps a 40-label plate cheap — geometry is shared, only the transform differs.
"""
from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAT_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
MODEL_PATH = "3D/3dmodel.model"

ET.register_namespace("", CORE_NS)
ET.register_namespace("m", MAT_NS)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


@dataclass
class Placement:
    """One copy of a rendered part, positioned on the plate."""
    source: Path      # a single-object 3MF produced by scad.render()
    x: float
    y: float
    z: float = 0.0


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _read_model(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as zf:
        return ET.fromstring(zf.read(MODEL_PATH))


def merge(placements: list[Placement], out_path: Path) -> Path:
    """Write a single 3MF containing every placement. Identical sources are reused."""
    if not placements:
        raise ValueError("nothing to place")

    model = ET.Element(_q(CORE_NS, "model"), {"unit": "millimeter"})
    resources = ET.SubElement(model, _q(CORE_NS, "resources"))
    build = ET.SubElement(model, _q(CORE_NS, "build"))

    next_id = 1
    object_for_source: dict[Path, int] = {}

    for p in placements:
        if p.source not in object_for_source:
            src = _read_model(p.source)
            src_resources = src.find(_q(CORE_NS, "resources"))
            if src_resources is None:
                raise ValueError(f"{p.source.name}: no <resources>")

            id_map: dict[str, str] = {}
            # Colour groups first — objects reference them by pid.
            for cg in src_resources.findall(_q(MAT_NS, "colorgroup")):
                old = cg.get("id")
                cg.set("id", str(next_id))
                if old:
                    id_map[old] = str(next_id)
                next_id += 1
                resources.append(cg)

            obj_id = None
            for obj in src_resources.findall(_q(CORE_NS, "object")):
                obj.set("id", str(next_id))
                obj_id = next_id
                next_id += 1
                obj_pid = obj.get("pid")
                if obj_pid in id_map:
                    obj.set("pid", id_map[obj_pid])
                mesh = obj.find(_q(CORE_NS, "mesh"))
                if mesh is not None:
                    triangles = mesh.find(_q(CORE_NS, "triangles"))
                    if triangles is not None:
                        for tri in triangles:
                            pid = tri.get("pid")
                            if pid in id_map:
                                tri.set("pid", id_map[pid])
                resources.append(obj)

            if obj_id is None:
                raise ValueError(f"{p.source.name}: no <object>")
            object_for_source[p.source] = obj_id

        transform = f"1 0 0 0 1 0 0 0 1 {p.x:g} {p.y:g} {p.z:g}"
        ET.SubElement(build, _q(CORE_NS, "item"), {
            "objectid": str(object_for_source[p.source]),
            "transform": transform,
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    xml = ET.tostring(model, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr(MODEL_PATH, xml)
    return out_path


def single(source: Path, out_path: Path) -> Path:
    """A one-label download — just hand back the render as-is."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out_path)
    return out_path


def layout(sizes: list[tuple[float, float]], plate_x: float = 250, plate_y: float = 250,
           gap: float = 3.0, margin: float = 5.0) -> tuple[list[tuple[float, float]], float, float]:
    """Shelf-pack parts (widest first is the caller's job) into rows on the plate.

    Returns (positions, used_x, used_y). Parts that don't fit raise ValueError —
    better a clear error than a silently truncated plate.
    """
    positions: list[tuple[float, float]] = []
    cx, cy, row_h = margin, margin, 0.0
    used_x = 0.0
    for w, h in sizes:
        if w > plate_x - 2 * margin:
            raise ValueError(f"a {w:.0f}mm label is wider than the {plate_x:.0f}mm plate")
        if cx + w > plate_x - margin:
            cx = margin
            cy += row_h + gap
            row_h = 0.0
        if cy + h > plate_y - margin:
            raise ValueError("plate is full — reduce quantities or split into two plates")
        positions.append((cx, cy))
        cx += w + gap
        used_x = max(used_x, cx - gap)
        row_h = max(row_h, h)
    return positions, used_x, cy + row_h
