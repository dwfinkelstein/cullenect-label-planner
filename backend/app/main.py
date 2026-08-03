"""Cullenect Label Planner API.

Serves the built React app plus a small JSON API over the tracked label library
and the OpenSCAD renderer.
"""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bulk, icons, scad, settings as settings_store, store, threemf
from .scad import RenderError
from .models import (FASTENER_DRIVERS, FASTENER_HEADS, FASTENER_SHAFTS,
                     FASTENER_THREADS, FONT_STYLES, FONTS, HARDWARE, Label)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cullenect")

app = FastAPI(title="Cullenect Label Planner", docs_url="/api/docs", openapi_url="/api/openapi.json")

STATIC_DIR = Path(__file__).parent.parent / "static"
MIME_3MF = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"


def _filename(stem: str, ext: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "label"
    return f"{safe[:60]}.{ext}"


def _download(path: Path, stem: str, ext: str) -> FileResponse:
    media = MIME_3MF if ext == "3mf" else "model/stl"
    return FileResponse(path, media_type=media, filename=_filename(stem, ext))


# ---------------------------------------------------------------- library CRUD

@app.get("/api/labels")
def api_list_labels() -> list[Label]:
    return store.list_labels()


@app.post("/api/labels", status_code=201)
def api_create_label(label: Label) -> Label:
    return store.add(label)


@app.put("/api/labels/{label_id}")
def api_update_label(label_id: str, label: Label) -> Label:
    updated = store.update(label_id, label)
    if not updated:
        raise HTTPException(404, "label not found")
    return updated


@app.delete("/api/labels/{label_id}", status_code=204)
def api_delete_label(label_id: str) -> Response:
    if not store.delete(label_id):
        raise HTTPException(404, "label not found")
    return Response(status_code=204)


@app.get("/api/settings")
def api_get_settings() -> settings_store.Settings:
    return settings_store.load()


@app.put("/api/settings")
def api_put_settings(settings: settings_store.Settings) -> settings_store.Settings:
    return settings_store.save(settings)


class BulkRequest(BaseModel):
    text: str                       # the pasted list, one label per line
    template: Label = Label()       # shared settings applied to every line


class BulkPreview(BaseModel):
    count: int
    labels: list[Label]


@app.post("/api/labels/bulk/preview")
def api_bulk_preview(req: BulkRequest) -> BulkPreview:
    """Parse without creating, so the UI can show exactly what a paste will produce."""
    labels = bulk.build_labels(req.text, req.template)
    return BulkPreview(count=len(labels), labels=labels)


@app.post("/api/labels/bulk", status_code=201)
def api_bulk_create(req: BulkRequest) -> list[Label]:
    labels = bulk.build_labels(req.text, req.template)
    if not labels:
        raise HTTPException(422, "nothing to add — every line was blank or a comment")
    if len(labels) > 200:
        raise HTTPException(422, f"{len(labels)} lines is more than the 200-label limit "
                                 "for one paste; split it up")
    return store.add_many(labels)


class ReorderRequest(BaseModel):
    order: list[str]


@app.post("/api/labels/reorder")
def api_reorder(req: ReorderRequest) -> list[Label]:
    return store.reorder(req.order)


@app.get("/api/library/export")
def api_export_library() -> JSONResponse:
    return JSONResponse(
        store.load().model_dump(),
        headers={"Content-Disposition": 'attachment; filename="cullenect-labels.json"'},
    )


class ImportRequest(BaseModel):
    labels: list[Label]


@app.post("/api/library/import")
def api_import_library(req: ImportRequest) -> list[Label]:
    return store.replace_all(req.labels)


# -------------------------------------------------------------------- renders

@app.post("/api/render/preview")
def api_preview(label: Label) -> FileResponse:
    """Render an unsaved label — this is what the live 3D preview polls."""
    try:
        path = scad.render_label(label, "3mf")
    except scad.RenderError as exc:
        raise HTTPException(422, str(exc))
    return FileResponse(path, media_type=MIME_3MF)


@app.get("/api/labels/{label_id}/download")
def api_download_label(label_id: str, fmt: str = "3mf") -> FileResponse:
    if fmt not in ("3mf", "stl"):
        raise HTTPException(400, "fmt must be 3mf or stl")
    label = store.get(label_id)
    if not label:
        raise HTTPException(404, "label not found")
    try:
        path = scad.render_label(label, fmt)
    except scad.RenderError as exc:
        raise HTTPException(422, str(exc))
    return _download(path, label.summary(), fmt)


@app.get("/api/accessories/{kind}")
def api_accessory(kind: str, width_u: float = 1, fmt: str = "3mf") -> FileResponse:
    try:
        path = scad.render_accessory(kind, width_u, fmt)
    except scad.RenderError as exc:
        raise HTTPException(422 if "unknown" not in str(exc) else 404, str(exc))
    return _download(path, f"cullenect-{kind}-{width_u:g}u", fmt)


# ---------------------------------------------------------------- picker icons

def _svg(path: Path) -> FileResponse:
    # Icons are pure functions of their parameters and are content-addressed on disk,
    # so they can be cached hard by the browser.
    return FileResponse(path, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=604800, immutable"})


@app.get("/api/icons/head.svg")
def api_icon_head(head: str, driver: str = "phillips", flange: bool = False) -> FileResponse:
    try:
        return _svg(icons.head_svg(head, driver, flange))
    except RenderError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/icons/driver.svg")
def api_icon_driver(driver: str) -> FileResponse:
    try:
        return _svg(icons.driver_svg(driver))
    except RenderError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/icons/fastener.svg")
def api_icon_fastener(head: str = "socket", driver: str = "phillips",
                      shaft: str = "machine", threads: str = "full",
                      flange: bool = False, security: bool = False) -> FileResponse:
    """The composed fastener — used for the shaft/threads rows and the summary chip."""
    try:
        return _svg(icons.fastener_svg(head, driver, shaft, threads, flange, security))
    except RenderError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/labels/{label_id}/thumbnail.svg")
def api_label_thumbnail(label_id: str) -> Response:
    """A small drawing of the label itself, for the library list.

    Derived from the label's own render, so it shows the real text and icons rather than a
    browser approximation of them. `v=<updated_at>` should be passed by the caller so the
    browser refetches when the label changes.
    """
    label = store.get(label_id)
    if not label:
        raise HTTPException(404, "label not found")
    return Response(icons.label_thumbnail_svg(label), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/icons/hardware.svg")
def api_icon_hardware(name: str) -> FileResponse:
    try:
        return _svg(icons.hardware_svg(name))
    except RenderError as exc:
        raise HTTPException(422, str(exc))


class PlateRequest(BaseModel):
    label_ids: list[str] = []          # empty = the whole library
    plate_x: float = 250
    plate_y: float = 250
    gap: float = 3.0


@app.post("/api/plate")
def api_plate(req: PlateRequest) -> FileResponse:
    """Render every requested label (qty copies each) onto one build plate."""
    library = store.list_labels()
    if req.label_ids:
        wanted = {i: n for n, i in enumerate(req.label_ids)}
        labels = sorted((l for l in library if l.id in wanted), key=lambda l: wanted[l.id])
    else:
        labels = library
    if not labels:
        raise HTTPException(400, "no labels selected")

    # Widest first packs the shelves tightly; copies of one label share geometry.
    copies: list[tuple[Label, Path]] = []
    try:
        for label in labels:
            path = scad.render_label(label, "3mf")
            copies.extend([(label, path)] * label.qty)
    except scad.RenderError as exc:
        raise HTTPException(422, str(exc))
    copies.sort(key=lambda c: -scad.label_size_mm(c[0])[0])

    sizes = [scad.label_size_mm(label) for label, _ in copies]
    try:
        positions, _, used_y = threemf.layout(sizes, req.plate_x, req.plate_y, req.gap)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    placements = [
        threemf.Placement(source=path, x=x, y=y)
        for (_, path), (x, y) in zip(copies, positions)
    ]
    out = Path(tempfile.mkdtemp(prefix="plate-")) / "plate.3mf"
    threemf.merge(placements, out)
    log.info("plate: %d parts, %.0fmm tall", len(placements), used_y)
    return _download(out, f"cullenect-plate-{len(placements)}", "3mf")


class PlatePlacement(BaseModel):
    """One part on the plate. The preview draws exactly these, so what you look at is the
    same packing the export produces rather than a second implementation of it."""
    label_id: str
    title: str
    x: float
    y: float
    w: float
    h: float


class PlateEstimate(BaseModel):
    parts: int
    rows: int
    used_y: float
    fits: bool
    message: str = ""
    plate_x: float = 250
    plate_y: float = 250
    placements: list[PlatePlacement] = []


@app.post("/api/plate/estimate")
def api_plate_estimate(req: PlateRequest) -> PlateEstimate:
    """Cheap layout-only check so the UI can warn before a slow render."""
    library = store.list_labels()
    labels = [l for l in library if not req.label_ids or l.id in set(req.label_ids)]
    # Same expansion and widest-first ordering as the real plate build, so the preview and
    # the export can't disagree about where anything sits.
    copies = [l for label in labels for l in [label] * label.qty]
    copies.sort(key=lambda l: -scad.label_size_mm(l)[0])
    sizes = [scad.label_size_mm(l) for l in copies]
    base = dict(plate_x=req.plate_x, plate_y=req.plate_y)
    if not sizes:
        return PlateEstimate(parts=0, rows=0, used_y=0, fits=False,
                             message="no labels selected", **base)
    try:
        positions, _, used_y = threemf.layout(sizes, req.plate_x, req.plate_y, req.gap)
    except ValueError as exc:
        return PlateEstimate(parts=len(sizes), rows=0, used_y=0, fits=False,
                             message=str(exc), **base)
    rows = len({round(y, 3) for _, y in positions})
    placements = [
        PlatePlacement(label_id=label.id, title=label.summary(), x=x, y=y, w=w, h=h)
        for label, (x, y), (w, h) in zip(copies, positions, sizes)
    ]
    return PlateEstimate(parts=len(sizes), rows=rows, used_y=used_y, fits=True,
                         placements=placements, **base)


# --------------------------------------------------------------------- health

@app.get("/api/meta")
def api_meta() -> dict:
    return {
        "fonts": FONTS,
        "font_styles": FONT_STYLES,
        "fastener_heads": FASTENER_HEADS,
        "fastener_shafts": FASTENER_SHAFTS,
        "fastener_threads": FASTENER_THREADS,
        "fastener_drivers": FASTENER_DRIVERS,
        "hardware": HARDWARE,
        "accessories": list(scad.ACCESSORIES),
        "fonts_missing": scad.missing_fonts(FONTS),
    }


@app.get("/api/health")
def api_health() -> dict:
    return {
        "ok": True,
        "openscad": scad.openscad_version(),
        "color_3mf": scad.supports_color_3mf(),
        "labels": len(store.list_labels()),
    }


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
