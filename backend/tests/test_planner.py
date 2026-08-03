"""Behavioural tests for the label planner.

Organised around the things that would otherwise fail SILENTLY — a substituted font, a
dropped label, an overlapping plate, an icon that renders as nothing. Several of these
exist because the behaviour they assert was assumed to hold and turned out not to.

Renderer-dependent tests skip when OpenSCAD isn't installed, so the rest runs anywhere:

    cd backend && python -m pytest tests -q
"""
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cull-test-"))
os.environ.setdefault("RENDER_CACHE", tempfile.mkdtemp(prefix="cull-cache-"))

from app import bulk, scad, store, threemf                      # noqa: E402
from app.models import Fastener, Label, TextBlock               # noqa: E402

HAVE_OPENSCAD = shutil.which(scad.OPENSCAD) is not None or Path(scad.OPENSCAD).exists()
needs_openscad = pytest.mark.skipif(not HAVE_OPENSCAD, reason="OpenSCAD not available")


@pytest.fixture(autouse=True)
def fresh_library(tmp_path, monkeypatch):
    """Point the store at a throwaway directory for every test."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "LIBRARY_PATH", tmp_path / "labels.json")
    yield


# --- the Gridfinity width formula --------------------------

@pytest.mark.parametrize("units,expected", [(1, 36), (2, 78), (3, 120), (0.5, 15)])
def test_label_width_follows_the_gridfinity_formula(units, expected):
    """printed width is (42 x units) - 6 mm."""
    label = Label(width_u=units)
    assert scad.label_size_mm(label) == (expected, 11.0)


# --- parameters are validated, not passed through to the renderer ------------------------

@pytest.mark.parametrize("field,value", [
    ("hardware", "not_a_real_icon"),
    ("text_color", "red"),
    ("text_color", "#GGGGGG"),
    ("width_u", 0),
    ("width_u", 99),
])
def test_bad_label_parameters_are_rejected(field, value):
    """an unknown/out-of-range parameter is rejected, not sent to the renderer.

    An unmatched value doesn't fail in OpenSCAD — the .scad's if-chain matches nothing and
    quietly renders the label with the icon missing.
    """
    with pytest.raises(ValidationError):
        Label(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("head", "banana"), ("driver", "banana"), ("shaft", "banana"), ("threads", "banana"),
])
def test_bad_fastener_parameters_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Fastener(**{field: value})


@pytest.mark.parametrize("field,value", [("font", "Comic Sans"), ("style", "Wobbly")])
def test_unavailable_fonts_are_rejected(field, value):
    """A font the image doesn't ship would be silently substituted by OpenSCAD."""
    with pytest.raises(ValidationError):
        TextBlock(**{field: value})


def test_every_offered_option_actually_validates():
    """The UI's option lists and the validators can't drift apart."""
    from app.models import (FASTENER_DRIVERS, FASTENER_HEADS, FASTENER_SHAFTS,
                            FASTENER_THREADS, FONTS, FONT_STYLES, HARDWARE)
    for h in FASTENER_HEADS: Fastener(head=h)
    for d in FASTENER_DRIVERS: Fastener(driver=d)
    for s in FASTENER_SHAFTS: Fastener(shaft=s)
    for t in FASTENER_THREADS: Fastener(threads=t)
    for w in HARDWARE: Label(hardware=w)
    for f in FONTS: TextBlock(font=f)
    for st in FONT_STYLES: TextBlock(style=st)


# --- the library: ids are stable, seeds persist ------------------------------

def test_seed_library_is_persisted_and_ids_are_stable():
    """ids are minted once and stable across reads; seeds are persisted.

    Regression test: the seed set was rebuilt per request, so every id
    the UI held was stale and save/delete 404'd.
    """
    first = [l.id for l in store.list_labels()]
    second = [l.id for l in store.list_labels()]
    assert first == second and all(first)
    assert store.LIBRARY_PATH.exists(), "seed library must be written on first load"


def test_update_and_delete_work_on_a_seeded_id():
    label = store.list_labels()[0]
    updated = store.update(label.id, label.model_copy(update={"name": "renamed"}))
    assert updated and updated.name == "renamed"
    assert store.get(label.id).name == "renamed"
    assert store.delete(label.id) is True
    assert store.get(label.id) is None
    assert store.delete(label.id) is False


# --- the library: durability -------------------------------------------------

def test_a_corrupt_library_is_preserved_not_discarded():
    """an unparseable library is moved aside, not overwritten or deleted."""
    store.list_labels()
    store.LIBRARY_PATH.write_text("{ this is not json")
    store.load()
    backups = list(store.LIBRARY_PATH.parent.glob("labels.corrupt.*.json"))
    assert backups, "the unreadable library must be kept"
    assert "not json" in backups[0].read_text()


def test_writes_are_atomic():
    """an interrupted save never leaves a partial library.

    The write goes to a temp file and is renamed, so a crash between the two leaves the
    previous good file untouched. Patched by hand rather than via monkeypatch, because
    undoing a monkeypatch here would also revert the fixture that redirects the store.
    """
    store.list_labels()
    good = store.LIBRARY_PATH.read_text()
    real_replace = Path.replace

    def boom(self, target):
        raise OSError("simulated crash between write and rename")

    Path.replace = boom
    try:
        with pytest.raises(OSError):
            store.add(Label(name="never lands"))
    finally:
        Path.replace = real_replace

    assert store.LIBRARY_PATH.read_text() == good, "the previous library must survive"
    json.loads(store.LIBRARY_PATH.read_text())      # still valid JSON
    assert not any(p.name.endswith(".json.tmp") and p.stat().st_size == 0
                   for p in store.LIBRARY_PATH.parent.iterdir())


def test_export_import_round_trips():
    """export produces a document import accepts, reproducing the labels."""
    original = store.list_labels()
    exported = json.loads(store.load().model_dump_json())
    store.replace_all([])
    assert store.list_labels() == []
    store.replace_all([Label.model_validate(l) for l in exported["labels"]])
    assert [l.name for l in store.list_labels()] == [l.name for l in original]


def test_reorder_persists_and_keeps_strays():
    ids = [l.id for l in store.list_labels()]
    store.reorder(list(reversed(ids[:3])))
    assert [l.id for l in store.list_labels()][:3] == list(reversed(ids[:3]))
    assert len(store.list_labels()) == len(ids), "reorder must not drop labels"


# --- plate packing --------------------------------------------------

def test_plate_layout_never_overlaps_and_stays_in_bounds():
    """parts are laid out without overlap and within the plate and gap."""
    sizes = [(36, 11)] * 20 + [(78, 11)] * 5 + [(120, 11)] * 3
    sizes.sort(key=lambda s: -s[0])
    plate_x = plate_y = 250
    gap = 3.0
    positions, used_x, used_y = threemf.layout(sizes, plate_x, plate_y, gap)
    assert len(positions) == len(sizes)
    rects = [(x, y, x + w, y + h) for (x, y), (w, h) in zip(positions, sizes)]
    for i, a in enumerate(rects):
        assert a[0] >= 0 and a[1] >= 0 and a[2] <= plate_x and a[3] <= plate_y
        for b in rects[i + 1:]:
            overlap = not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
            assert not overlap, f"parts overlap: {a} and {b}"
    assert used_y <= plate_y


def test_plate_refuses_rather_than_truncating():
    """A plate that doesn't fit is refused with a reason, never silently cut."""
    with pytest.raises(ValueError, match="plate is full"):
        threemf.layout([(36, 11)] * 5000, 250, 250, 3.0)
    with pytest.raises(ValueError, match="wider than"):
        threemf.layout([(400, 11)], 250, 250, 3.0)


# --- bulk paste ----------------------------------------------------------------------

def test_paste_parses_lines_separators_and_comments():
    parsed = bulk.parse_lines("M3 x 12\n\n  M4 x 20 | 10pcs \n# a comment\nFerrules\tblue\n")
    assert parsed == [("M3 x 12", ""), ("M4 x 20", "10pcs"), ("Ferrules", "blue")]


def test_paste_applies_the_shared_template_to_every_line():
    template = Label(width_u=2, surface="deboss", hardware="washer",
                     fastener=Fastener(show=True, head="pan", driver="torx"), qty=3)
    labels = bulk.build_labels("M3 washers\nM4 washers", template)
    assert len(labels) == 2
    for l in labels:
        assert (l.width_u, l.surface, l.hardware, l.qty) == (2, "deboss", "washer", 3)
        assert (l.fastener.head, l.fastener.driver) == ("pan", "torx")
        assert l.id == "" and l.created_at is None      # ids are minted by the store
    assert [l.text1.text for l in labels] == ["M3 washers", "M4 washers"]
    assert [l.name for l in labels] == ["M3 washers", "M4 washers"], "name defaults to text"


def test_paste_of_only_blanks_produces_nothing():
    assert bulk.build_labels("\n\n#comment\n   \n", Label()) == []


def test_bulk_add_is_one_write_and_mints_ids():
    before = len(store.list_labels())
    created = store.add_many(bulk.build_labels("a\nb\nc", Label()))
    assert len(created) == 3 and all(l.id for l in created)
    assert len({l.id for l in created}) == 3
    assert len(store.list_labels()) == before + 3


# --- renderer (skipped without OpenSCAD) ----------------------------------------------

def test_scad_value_serialization():
    """each field serializes to the OpenSCAD literal form for its type."""
    assert scad._scad_value(True) == "true"
    assert scad._scad_value(False) == "false"
    assert scad._scad_value([1, -2.5]) == "[1,-2.5]"
    assert scad._scad_value('say "hi"') == '"say \\"hi\\""'
    assert scad._scad_value("M3 x 12") == '"M3 x 12"'


def test_label_defines_cover_every_customizer_parameter():
    """every customizer parameter has a corresponding field."""
    defines = scad.label_defines(Label())
    expected = {
        "Select_Output", "label_width", "backward_compatible", "label_surface", "Text_Color",
        "Text1", "Text1_Align", "Text1_Font_Size", "Text1_Font", "Text1_Font_Style", "Text1_XY",
        "Text2", "Text2_Align", "Text2_Font_Size", "Text2_Font", "Text2_Font_Style", "Text2_XY",
        "Show_Fastener", "Fastener_Head", "Fastener_Shaft", "Fastener_Threads",
        "Fastener_Driver", "Fastener_Head_Flange", "Fastener_Driver_Security",
        "Select_Hardware",
    }
    assert expected <= set(defines)


def test_library_only_metadata_never_reaches_the_geometry():
    """changing name/qty/tags alone produces an identical render."""
    a = Label(name="one", qty=1, tags=["x"])
    b = Label(name="two", qty=9, tags=["y", "z"])
    assert scad.label_defines(a) == scad.label_defines(b)


@needs_openscad
def test_render_is_cached_and_colored(tmp_path, monkeypatch):
    """renders are content-addressed and cached; 3MF carries a colour group."""
    monkeypatch.setattr(scad, "CACHE_DIR", tmp_path)
    label = Label(text1=TextBlock(text="CACHE"), text_color="#CC2222")
    first = scad.render_label(label, "3mf")
    stamp = first.stat().st_mtime_ns
    second = scad.render_label(label, "3mf")
    assert second == first and second.stat().st_mtime_ns == stamp, "should not re-render"

    with zipfile.ZipFile(first) as zf:
        model = zf.read("3D/3dmodel.model").decode()
    assert "colorgroup" in model
    assert "#CC2222" in model.upper().replace("CC2222FF", "CC2222")


@needs_openscad
def test_plate_merge_shares_geometry_per_distinct_label(tmp_path, monkeypatch):
    """One object per distinct label, one item transform per copy."""
    monkeypatch.setattr(scad, "CACHE_DIR", tmp_path)
    src = scad.render_label(Label(text1=TextBlock(text="X")), "3mf")
    placements = [threemf.Placement(source=src, x=i * 40, y=0) for i in range(4)]
    out = threemf.merge(placements, tmp_path / "plate.3mf")
    with zipfile.ZipFile(out) as zf:
        model = zf.read("3D/3dmodel.model").decode()
    assert model.count("<object ") == 1, "identical labels must share one object"
    assert model.count("<item ") == 4, "one item transform per copy"
    assert "colorgroup" in model, "colour must survive the merge"


@needs_openscad
def test_concurrent_renders_of_the_same_label_do_not_collide(tmp_path, monkeypatch):
    """The UI renders the same label twice at once — preview and fit check.

    Writing straight to the cache path made those two clobber each other's output file,
    and one would fail on a truncated or missing result. Rendering to a unique temp path
    and renaming into place makes the race harmless.
    """
    import concurrent.futures

    monkeypatch.setattr(scad, "CACHE_DIR", tmp_path)
    label = Label(text1=TextBlock(text="RACE"), width_u=2.2)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = [f.result() for f in
                   [pool.submit(scad.render_label, label, "3mf") for _ in range(4)]]

    assert len({str(r) for r in results}) == 1, "all four should agree on the cache entry"
    assert results[0].stat().st_size > 0
    assert not list(tmp_path.glob("*.tmp*")), "no temp files should be left behind"
