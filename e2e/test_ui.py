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
import re

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
    """Open the app ready to use — past the first-run intro, as a returning user would be.

    The intro is a modal, so leaving it up would block every other test on an overlay
    rather than on anything the test is about. Its own behaviour is covered separately by
    test_a_first_visit_explains_the_system_and_credits_upstream.
    """
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(1500)
    intro = page.get_by_role("dialog", name="About Cullenect labels")
    if intro.count():
        intro.get_by_role("button", name="Got it").click()
        page.wait_for_timeout(400)
    page.wait_for_timeout(2000)
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


def test_a_first_visit_explains_the_system_and_credits_upstream(browser):
    """For some people this tool is how they first meet Cullenect labels."""
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    page.goto(BASE, wait_until="networkidle", timeout=60_000)
    try:
        intro = page.get_by_role("dialog", name="About Cullenect labels")
        expect(intro).to_be_visible(timeout=10_000)
        text = intro.inner_text()
        assert "click" in text.lower(), "it should say the label clicks into a slot"
        assert "Cullen J Webb" in text, "upstream must be credited by name"
        links = intro.locator("a[href*='CullenJWebb/Cullenect-Labels']").count()
        assert links >= 1, "upstream must be linked, not just named"

        intro.get_by_role("button", name="Got it").click()
        expect(intro).not_to_be_visible()

        # Dismissed for good, but still reachable on demand.
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2500)
        expect(page.get_by_role("dialog", name="About Cullenect labels")).not_to_be_visible()
        page.get_by_title("What are Cullenect labels?").click()
        expect(page.get_by_role("dialog", name="About Cullenect labels")).to_be_visible()
    finally:
        page.close()


def test_the_socket_accessories_are_reachable_and_downloadable(browser):
    """The API had these all along; there was no way to get at them from the UI."""
    page = open_app(browser, 1500, 950)
    try:
        page.get_by_role("button", name="Sockets").click()
        dialog = page.get_by_role("dialog", name="Sockets and test fits")
        expect(dialog).to_be_visible()

        # every accessory the API offers is listed
        offered = page.request.get(f"{BASE}/api/meta").json()["accessories"]
        options = dialog.locator("#acc-kind option").count()
        assert options >= len(offered) - 1, \
            f"UI lists {options} parts, the API offers {len(offered)}"

        # each one explains what it's for
        assert len(dialog.inner_text()) > 200, "the parts need explaining, not just naming"

        # and it renders rather than sitting blank
        expect(dialog.locator("canvas")).to_be_visible()
        page.wait_for_timeout(6000)
        assert not page.errors, f"console errors: {page.errors[:2]}"

        # the download actually produces a model
        r = page.request.get(f"{BASE}/api/accessories/socket-negative?width_u=1&fmt=3mf")
        assert r.status == 200 and len(r.body()) > 500
    finally:
        page.close()


def test_tags_can_be_added_and_used_to_filter(browser):
    """Tags were stored and searched but there was no way to set one."""
    page = open_app(browser, 1500, 950)
    try:
        page.get_by_role("button", name="+ New label").click()
        dialog = page.get_by_role("dialog", name="New label")
        dialog.locator("#nl-t1").fill("E2E tagged")
        tags = dialog.locator("#tag-input")
        tags.scroll_into_view_if_needed()
        tags.fill("e2e-group")
        tags.press("Enter")
        dialog.get_by_role("button", name="Add label").click()
        page.wait_for_timeout(2000)

        created = [l for l in page.request.get(f"{BASE}/api/labels").json()
                   if l["text1"]["text"] == "E2E tagged"]
        assert created and created[-1]["tags"] == ["e2e-group"], "the tag must persist"

        # Filtering to the tag narrows the list to just that label.
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="e2e-group", exact=True).first.click()
        page.wait_for_timeout(600)
        rows = page.locator("ul li").count()
        assert rows == 1, f"filtering by tag should leave 1 row, saw {rows}"

        page.request.delete(f"{BASE}/api/labels/{created[-1]['id']}")
    finally:
        page.close()


def test_text_that_overflows_is_flagged_with_a_fix(browser):
    """Without this the overflow is invisible until after the print."""
    page = open_app(browser, 1500, 950)
    try:
        page.get_by_role("button", name="+ New label").click()
        dialog = page.get_by_role("dialog", name="New label")
        dialog.locator("#nl-t1").fill("M3 x 12 socket cap screws")
        # Generous: on a cold cache a fit check renders the label several times while it
        # verifies a size that actually fits, and CI always starts cold.
        warning = dialog.get_by_text("This won't fit on the label.")
        expect(warning).to_be_visible(timeout=90_000)

        # The offered fix must actually resolve it, not just acknowledge the problem.
        dialog.get_by_role("button", name=re.compile(r"^Use a .*U label$")).click()
        expect(warning).not_to_be_visible(timeout=90_000)
        dialog.get_by_role("button", name="Cancel").click()
    finally:
        page.close()


def test_a_dialog_traps_and_restores_focus(browser):
    """Without a trap, tabbing walks out of the dialog into the page it's covering."""
    page = open_app(browser, 1400, 950)
    try:
        opener = page.get_by_role("button", name="+ New label")
        opener.click()
        dialog = page.get_by_role("dialog", name="New label")
        expect(dialog).to_be_visible()

        # Focus starts inside.
        assert page.evaluate(
            "() => !!document.querySelector('[role=dialog]')?.contains(document.activeElement)"
        ), "focus should move into the dialog when it opens"

        # And stays inside, however far you tab.
        for _ in range(40):
            page.keyboard.press("Tab")
        assert page.evaluate(
            "() => !!document.querySelector('[role=dialog]')?.contains(document.activeElement)"
        ), "tabbing escaped the dialog into the page behind it"

        # Backwards too.
        for _ in range(15):
            page.keyboard.press("Shift+Tab")
        assert page.evaluate(
            "() => !!document.querySelector('[role=dialog]')?.contains(document.activeElement)"
        ), "shift-tabbing escaped the dialog"

        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()

        # And focus comes back to what opened it, not the top of the document.
        assert page.evaluate(
            "() => document.activeElement?.textContent?.includes('New label')"
        ), "focus should return to the control that opened the dialog"
    finally:
        page.close()
