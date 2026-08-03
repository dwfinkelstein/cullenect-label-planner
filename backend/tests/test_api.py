"""API-level tests: the guarantees a caller relies on.

`test_planner.py` covers the domain logic directly; this covers the behaviour through the
HTTP surface, plus the parts of the renderer contract that only show up at the edges —
what a failed render returns, what the cache is keyed on, whether the preview really is
the same bytes as the export.

Renderer-dependent tests skip when OpenSCAD isn't installed.
"""
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cull-api-"))
os.environ.setdefault("RENDER_CACHE", tempfile.mkdtemp(prefix="cull-api-cache-"))

from app import scad, store                                    # noqa: E402
from app.main import app                                       # noqa: E402
from app.models import Label, TextBlock                        # noqa: E402

HAVE_OPENSCAD = shutil.which(scad.OPENSCAD) is not None or Path(scad.OPENSCAD).exists()
needs_openscad = pytest.mark.skipif(not HAVE_OPENSCAD, reason="OpenSCAD not available")

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_library(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "LIBRARY_PATH", tmp_path / "labels.json")
    yield


# --- the option lists the UI is built from --------------------------------------------

def test_meta_lists_every_option_the_ui_offers():
    meta = client.get("/api/meta").json()
    for key in ("fonts", "font_styles", "fastener_heads", "fastener_shafts",
                "fastener_threads", "fastener_drivers", "hardware", "accessories"):
        assert meta[key], f"{key} must not be empty"
    assert "fonts_missing" in meta, "a substituted font must be reportable"


def test_health_reports_the_renderer_and_its_colour_capability():
    """Colour capability is renderer-dependent, so it has to be visible, not assumed."""
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert isinstance(health["color_3mf"], bool)
    assert health["openscad"]


# --- validation reaches the HTTP edge -------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"hardware": "no_such_icon"},
    {"text_color": "not-a-colour"},
    {"width_u": 0},
    {"fastener": {"head": "no_such_head"}},
    {"text1": {"font": "Comic Sans"}},
])
def test_invalid_labels_are_rejected_with_422(payload):
    assert client.post("/api/labels", json=payload).status_code == 422


def test_a_valid_label_round_trips_through_the_api():
    created = client.post("/api/labels", json={"name": "api", "text1": {"text": "M3"}}).json()
    assert created["id"]
    assert client.get("/api/labels").json()[-1]["id"] == created["id"]
    updated = client.put(f"/api/labels/{created['id']}",
                         json={**created, "name": "renamed"}).json()
    assert updated["name"] == "renamed"
    assert client.delete(f"/api/labels/{created['id']}").status_code == 204
    assert client.delete(f"/api/labels/{created['id']}").status_code == 404


# --- paste ----------------------------------------------------------------------------

def test_bulk_preview_reports_exactly_what_would_be_created():
    body = {"text": "A\nB | second\n# comment\n\nC", "template": {"width_u": 2}}
    preview = client.post("/api/labels/bulk/preview", json=body).json()
    assert preview["count"] == 3
    assert [l["text1"]["text"] for l in preview["labels"]] == ["A", "B", "C"]
    assert preview["labels"][1]["text2"]["text"] == "second"
    assert all(l["width_u"] == 2 for l in preview["labels"])

    created = client.post("/api/labels/bulk", json=body).json()
    assert [l["text1"]["text"] for l in created] == ["A", "B", "C"], \
        "creating must produce what the preview promised"


def test_an_empty_paste_creates_nothing():
    assert client.post("/api/labels/bulk", json={"text": "\n# only a comment\n"}).status_code == 422


# --- plate ----------------------------------------------------------------------------

def test_estimate_agrees_with_what_the_plate_would_contain():
    """The preview and the export must not disagree about the packing."""
    ids = []
    for i, qty in enumerate([1, 3, 2]):
        r = client.post("/api/labels", json={"name": f"p{i}", "qty": qty,
                                             "text1": {"text": f"P{i}"}}).json()
        ids.append(r["id"])
    est = client.post("/api/plate/estimate",
                      json={"label_ids": ids, "plate_x": 250, "plate_y": 250, "gap": 3}).json()
    assert est["fits"] is True
    assert est["parts"] == 6, "quantities must be expanded"
    assert len(est["placements"]) == est["parts"], "one placement per part"
    assert est["rows"] == len({round(p["y"], 3) for p in est["placements"]})
    # every placement sits inside the plate
    for p in est["placements"]:
        assert 0 <= p["x"] and p["x"] + p["w"] <= est["plate_x"]
        assert 0 <= p["y"] and p["y"] + p["h"] <= est["plate_y"]


def test_a_plate_that_cannot_fit_is_reported_as_not_fitting():
    r = client.post("/api/labels", json={"name": "many", "qty": 50,
                                         "text1": {"text": "X"}}).json()
    est = client.post("/api/plate/estimate",
                      json={"label_ids": [r["id"]], "plate_x": 40, "plate_y": 20,
                            "gap": 3}).json()
    assert est["fits"] is False and est["message"], \
        "an impossible plate must say so before the slow render"


@needs_openscad
def test_building_an_impossible_plate_is_refused_not_truncated():
    r = client.post("/api/labels", json={"name": "many", "qty": 50,
                                         "text1": {"text": "X"}}).json()
    assert client.post("/api/plate", json={"label_ids": [r["id"]], "plate_x": 40,
                                           "plate_y": 20, "gap": 3}).status_code == 422


def test_a_misconfigured_renderer_reports_itself_instead_of_crashing(monkeypatch):
    """A missing binary used to surface as a 500 with a stack trace and no cause."""
    monkeypatch.setattr(scad, "OPENSCAD", "/definitely/not/openscad")
    with pytest.raises(scad.RenderError) as exc:
        scad.render({"Select_Output": 0}, "3mf")
    assert "/definitely/not/openscad" in str(exc.value)
    assert "OPENSCAD_BIN" in str(exc.value), "the message should say how to fix it"


def test_a_plate_with_nothing_selected_is_refused():
    assert client.post("/api/plate", json={"label_ids": ["nope"]}).status_code == 400


# --- accessories ----------------------------------------------------------------------

def test_an_unknown_accessory_is_rejected():
    """A typo must not quietly render something arbitrary."""
    assert client.get("/api/accessories/not-a-real-accessory").status_code == 404


@needs_openscad
@pytest.mark.parametrize("kind", ["socket-test-fit", "socket-negative", "label-spacer"])
def test_each_accessory_exports(kind):
    r = client.get(f"/api/accessories/{kind}?width_u=1")
    assert r.status_code == 200 and len(r.content) > 500


# --- icons ----------------------------------------------------------------------------

@needs_openscad
def test_icon_endpoints_return_svg():
    for url in ("/api/icons/head.svg?head=socket",
                "/api/icons/driver.svg?driver=hex",
                "/api/icons/hardware.svg?name=washer",
                "/api/icons/fastener.svg?head=pan&driver=torx&shaft=machine&threads=full"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert r.content.lstrip().startswith(b"<?xml"), url
        assert b"<path" in r.content, f"{url} produced an empty drawing"


# --- renderer contract ------------------------------------------------------------------

@needs_openscad
def test_the_preview_is_byte_identical_to_the_export():
    """The preview is only trustworthy if it IS the exported file."""
    label = {"name": "same", "text1": {"text": "SAME"}}
    created = client.post("/api/labels", json=label).json()
    preview = client.post("/api/render/preview", json=created).content
    export = client.get(f"/api/labels/{created['id']}/download?fmt=3mf").content
    assert preview == export


@needs_openscad
def test_stl_and_3mf_describe_the_same_solid():
    created = client.post("/api/labels", json={"name": "fmt",
                                               "text1": {"text": "FMT"}}).json()
    three = client.get(f"/api/labels/{created['id']}/download?fmt=3mf")
    stl = client.get(f"/api/labels/{created['id']}/download?fmt=stl")
    assert three.status_code == stl.status_code == 200
    with zipfile.ZipFile(__import__("io").BytesIO(three.content)) as zf:
        model = zf.read("3D/3dmodel.model").decode()
    tri_3mf = model.count("<triangle ")
    tri_stl = stl.content.count(b"facet normal") or int.from_bytes(stl.content[80:84], "little")
    assert tri_3mf > 0 and tri_stl > 0
    assert abs(tri_3mf - tri_stl) / tri_3mf < 0.01, \
        "the two formats should describe the same mesh"


@needs_openscad
def test_a_failed_render_reports_why_and_leaves_no_partial_file(tmp_path, monkeypatch):
    """A half-written artifact in the cache would be served forever as if it were good."""
    monkeypatch.setattr(scad, "CACHE_DIR", tmp_path)
    bad = tmp_path / "broken.scad"
    bad.write_text("this is not valid openscad ;;;\n")
    monkeypatch.setattr(scad, "SCAD_FILE", bad)
    with pytest.raises(scad.RenderError) as exc:
        scad.render_label(Label(text1=TextBlock(text="X")), "3mf")
    assert str(exc.value), "the renderer's own diagnostics must reach the caller"
    assert not list(tmp_path.glob("*.3mf")), "no partial artifact may be left behind"


@needs_openscad
def test_the_cache_key_covers_the_geometry_file(tmp_path, monkeypatch):
    """Editing the vendored .scad must invalidate previous renders."""
    monkeypatch.setattr(scad, "CACHE_DIR", tmp_path)
    label = Label(text1=TextBlock(text="KEY"))
    first = scad.render_label(label, "3mf")
    # touch the geometry file: same parameters, different source
    src = Path(scad.SCAD_FILE)
    src.touch()
    second = scad.render_label(label, "3mf")
    assert second != first, "a changed geometry file must produce a different cache entry"


# --- what ships -------------------------------------------------------------------------

def test_the_vendored_geometry_ships_with_its_licence():
    scad_dir = Path(scad.SCAD_FILE).parent
    assert (scad_dir / "LICENSE.upstream").is_file(), \
        "the upstream licence must ship alongside the vendored file"
    notice = (Path(__file__).resolve().parents[2] / "NOTICE").read_text()
    assert "Cullen J Webb" in notice
    assert "bd451b6" in notice, "the vendored commit must be pinned in NOTICE"


def test_the_renderer_is_pinned_to_an_exact_build():
    """An unpinned nightly would make renders irreproducible between rebuilds."""
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    line = next(l for l in dockerfile.splitlines() if "OPENSCAD_APPIMAGE" in l and "http" in l)
    assert "snapshots/OpenSCAD-20" in line and ".AppImage" in line
    assert "latest" not in line.lower(), "the renderer must not float"


# --- printer settings -------------------------------------------------------------------

def test_plate_settings_persist(tmp_path, monkeypatch):
    """Plate size is a property of the printer — re-entering it every visit is the bug."""
    from app import settings as settings_store
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")

    assert client.get("/api/settings").json() == {"plate_x": 250, "plate_y": 250, "gap": 3}
    saved = client.put("/api/settings",
                       json={"plate_x": 256, "plate_y": 256, "gap": 2.5}).json()
    assert saved["plate_x"] == 256
    assert client.get("/api/settings").json()["plate_y"] == 256, "must survive a fresh read"


def test_bad_plate_settings_are_rejected():
    assert client.put("/api/settings", json={"plate_x": 0, "plate_y": 250,
                                             "gap": 3}).status_code == 422
    assert client.put("/api/settings", json={"plate_x": 250, "plate_y": 250,
                                             "gap": -1}).status_code == 422


def test_unreadable_settings_fall_back_to_defaults(tmp_path, monkeypatch):
    """A corrupt settings file must not stop the app from starting."""
    from app import settings as settings_store
    bad = tmp_path / "settings.json"
    bad.write_text("{ not json")
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", bad)
    assert settings_store.load().plate_x == 250
