"""Browser tests for the behaviour a unit test can't see.

Two classes of thing live here:

1. **Layout.** This app has twice shipped a layout that made it unusable — once below
   1024px, where the editor was laid out past the bottom edge of a container that could
   not scroll, and once at 3440px, where one column absorbed the surplus width and pushed
   the editor a screen away from the list. Both passed a screenshot check at a single
   convenient width. So layout is checked across a SWEEP, and asserted on reachability
   rather than appearance.

2. **Flows.** That creating a label through the dialog really persists the choices that
   were clicked, that a pasted list becomes the labels it previewed, and that the plate
   preview reports progress and completes.

Run against a running instance:

    pip install pytest playwright && playwright install chromium
    E2E_BASE_URL=http://localhost:8080 pytest e2e -q
"""
import os

import pytest
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8080")

# Widths that have historically broken, plus the ordinary ones between them.
WIDTHS = [(3440, 1000), (1600, 950), (1280, 800), (1024, 768), (900, 800), (390, 844)]


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader",
        ])
        yield b
        b.close()


def open_app(browser, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(3000)
    page.errors = errors
    return page


# --- layout ---------------------------------------------------------------------------

@pytest.mark.parametrize("width,height", WIDTHS)
def test_the_page_never_scrolls_sideways(browser, width, height):
    page = open_app(browser, width, height)
    try:
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        ), "content wider than the viewport pushes controls out of reach"
    finally:
        page.close()


@pytest.mark.parametrize("width,height", WIDTHS)
def test_the_preview_keeps_a_usable_size(browser, width, height):
    page = open_app(browser, width, height)
    try:
        page.wait_for_timeout(2500)
        box = page.locator("canvas").first.bounding_box()
        assert box and box["height"] >= 240, \
            f"preview collapsed to {box and round(box['height'])}px — unreadable"
    finally:
        page.close()


@pytest.mark.parametrize("width,height", WIDTHS)
def test_a_label_can_be_edited_at_any_width(browser, width, height):
    """The editor has been unreachable twice. Prove it's reachable AND usable."""
    page = open_app(browser, width, height)
    try:
        row = page.locator("ul li").first
        row.hover()
        row.get_by_role("button", name="✎").click()
        dialog = page.get_by_role("dialog", name="Edit label")
        expect(dialog).to_be_visible(timeout=10_000)
        text = dialog.locator("#nl-t1")
        text.scroll_into_view_if_needed()
        text.fill("edited at this width")
        assert text.input_value() == "edited at this width"
        dialog.get_by_role("button", name="Cancel").click()
        assert not page.errors, f"console errors: {page.errors[:2]}"
    finally:
        page.close()


# --- flows ----------------------------------------------------------------------------

def test_creating_a_label_persists_the_choices_that_were_clicked(browser):
    page = open_app(browser, 1500, 950)
    try:
        page.get_by_role("button", name="+ New label").click()
        dialog = page.get_by_role("dialog", name="New label")
        dialog.locator("#nl-t1").fill("E2E screw")
        dialog.get_by_label("Include a fastener icon").check()
        page.wait_for_timeout(3000)          # icons render server-side on first use
        dialog.get_by_title("Countersunk").first.click()
        dialog.get_by_title("Torx").first.click()
        dialog.get_by_role("button", name="Add label").click()
        page.wait_for_timeout(2000)

        created = page.request.get(f"{BASE}/api/labels").json()
        mine = [l for l in created if l["text1"]["text"] == "E2E screw"]
        assert mine, "the label was not created"
        label = mine[-1]
        assert label["fastener"]["head"] == "countersunk"
        assert label["fastener"]["driver"] == "torx"
        assert label["name"] == "E2E screw", "the name should default to the text"
        page.request.delete(f"{BASE}/api/labels/{label['id']}")
    finally:
        page.close()


def test_a_pasted_list_becomes_the_labels_it_previewed(browser):
    page = open_app(browser, 1500, 950)
    try:
        page.get_by_role("button", name="Paste a list").click()
        dialog = page.get_by_role("dialog", name="Paste a list")
        dialog.locator("#bulk-text").fill("E2E one\nE2E two | second\n# skipped\n\nE2E three")
        page.wait_for_timeout(600)
        expect(dialog.get_by_role("heading", name="3 labels")).to_be_visible()
        dialog.locator("footer button", has_text="Add").click()
        page.wait_for_timeout(2500)

        labels = page.request.get(f"{BASE}/api/labels").json()
        mine = [l for l in labels if l["text1"]["text"].startswith("E2E ")]
        assert [l["text1"]["text"] for l in mine] == ["E2E one", "E2E two", "E2E three"]
        assert mine[1]["text2"]["text"] == "second"
        for l in mine:
            page.request.delete(f"{BASE}/api/labels/{l['id']}")
    finally:
        page.close()


def test_the_plate_preview_reports_progress_and_completes(browser):
    page = open_app(browser, 1500, 950)
    try:
        page.get_by_role("button", name="Preview plate").click()
        dialog = page.get_by_role("dialog", name="Plate preview")
        expect(dialog).to_be_visible()
        # It reports which item it is on rather than sitting blank...
        expect(dialog.get_by_text("Rendering")).to_be_visible(timeout=15_000)
        # ...and finishes.
        expect(dialog.get_by_text("rendered")).to_be_visible(timeout=180_000)
        assert not page.errors, f"console errors: {page.errors[:2]}"
    finally:
        page.close()
