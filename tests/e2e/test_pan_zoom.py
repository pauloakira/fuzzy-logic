"""Browser tests for panning and zooming the canvas.

A diagram bigger than the viewport is unusable without these, and the awkward
part is not the transform — it is that an edit must not throw the user's view
away, while opening a different diagram must frame it afresh.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

EX1 = "exercises/exercicio1_motor_control/diagram.json"
EX2 = "exercises/exercicio2_sdof_vibration_control/diagram.json"


@pytest.fixture(autouse=True)
def _no_console_errors(page_errors):
    yield
    assert page_errors == [], f"page reported errors: {page_errors}"


def open_diagram(page: Page, server: str, path: str = EX2) -> None:
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    page.locator(f"[data-diagram-path='{path}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()


def view(page: Page) -> dict[str, float]:
    box = page.get_by_test_id("canvas").get_attribute("viewBox")
    x, y, w, h = (float(v) for v in box.split())
    return {"x": x, "y": y, "w": w, "h": h}


def wheel(page: Page, delta: int, at: tuple[float, float] | None = None) -> None:
    canvas = page.get_by_test_id("canvas")
    box = canvas.bounding_box()
    x, y = at or (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.move(x, y)
    page.mouse.wheel(0, delta)


# ----- zoom ---------------------------------------------------------------------


def test_the_diagram_starts_framed(page: Page, server: str):
    open_diagram(page, server)
    v = view(page)
    assert v["w"] > 700  # spans the whole diagram
    expect(page.get_by_test_id("zoom-level")).to_have_text("100%")


def test_wheeling_up_zooms_in(page: Page, server: str):
    open_diagram(page, server)
    before = view(page)
    wheel(page, -120)
    after = view(page)
    assert after["w"] < before["w"]
    # aspect is preserved, so zooming never distorts or letterboxes
    assert after["h"] / after["w"] == pytest.approx(before["h"] / before["w"], rel=1e-4)


def test_repeated_zooming_does_not_drift_the_aspect_ratio(page: Page, server: str):
    """The viewBox is the only store of the view, so rounding it compounds."""
    open_diagram(page, server)
    first = view(page)
    for _ in range(20):
        page.get_by_test_id("zoom-in").click()
    for _ in range(20):
        page.get_by_test_id("zoom-out").click()
    last = view(page)
    assert last["h"] / last["w"] == pytest.approx(first["h"] / first["w"], rel=1e-4)


def test_wheeling_down_zooms_out(page: Page, server: str):
    open_diagram(page, server)
    before = view(page)
    wheel(page, 120)
    assert view(page)["w"] > before["w"]


def test_zoom_keeps_the_point_under_the_cursor_fixed(page: Page, server: str):
    """Zooming toward a corner must not recentre the diagram."""
    open_diagram(page, server)
    box = page.get_by_test_id("canvas").bounding_box()
    # a point well left of centre
    at = (box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2)
    before = view(page)
    under_cursor = before["x"] + before["w"] * 0.2

    wheel(page, -120, at)
    after = view(page)
    still_under_cursor = after["x"] + after["w"] * 0.2
    assert still_under_cursor == pytest.approx(under_cursor, abs=2.0)


def zoom_of(page: Page) -> float:
    return float(page.get_by_test_id("canvas").get_attribute("data-zoom"))


def test_zoom_buttons_and_level_readout(page: Page, server: str):
    open_diagram(page, server)
    page.get_by_test_id("zoom-in").click()
    expect(page.get_by_test_id("zoom-level")).not_to_have_text("100%")
    assert zoom_of(page) > 1

    page.get_by_test_id("zoom-out").click()
    assert zoom_of(page) == pytest.approx(1.0, abs=0.01)


def test_zoom_is_bounded(page: Page, server: str):
    open_diagram(page, server)
    for _ in range(40):
        page.get_by_test_id("zoom-in").click()
    assert zoom_of(page) <= 6.01
    for _ in range(80):
        page.get_by_test_id("zoom-out").click()
    assert zoom_of(page) >= 0.149


# ----- pan ----------------------------------------------------------------------


def test_dragging_the_background_pans(page: Page, server: str):
    open_diagram(page, server)
    before = view(page)
    box = page.get_by_test_id("canvas").bounding_box()
    # a corner of the canvas, clear of any block
    x, y = box["x"] + 12, box["y"] + box["height"] - 12
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 80, y - 40, steps=6)
    page.mouse.up()

    after = view(page)
    assert after["x"] < before["x"]          # content moved right with the cursor
    assert after["y"] > before["y"]
    assert after["w"] == pytest.approx(before["w"])  # panning is not zooming


def test_dragging_a_node_moves_the_node_not_the_view(page: Page, server: str):
    """Node, wire and port drags have their own handlers; only empty space pans."""
    open_diagram(page, server)
    before = view(page)
    node = page.locator(".node[data-block='plant']")
    box = node.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 40, box["y"] + box["height"] / 2,
                    steps=6)
    page.mouse.up()

    assert view(page)["x"] == pytest.approx(before["x"], abs=0.01)
    expect(page.get_by_test_id("dirty")).to_be_visible()


# ----- the view survives editing --------------------------------------------------


def test_an_edit_does_not_reset_the_view(page: Page, server: str):
    """Refitting on every edit would snap the diagram back on each keystroke."""
    open_diagram(page, server)
    wheel(page, -120)
    zoomed = view(page)

    page.locator(".node[data-block='force']").click()
    page.locator("[data-param='omega']").fill("7")
    page.locator("[data-param='omega']").blur()
    expect(page.get_by_test_id("dirty")).to_be_visible()

    assert view(page)["w"] == pytest.approx(zoomed["w"], abs=0.01)


def test_fit_restores_the_whole_diagram(page: Page, server: str):
    open_diagram(page, server)
    framed = view(page)
    wheel(page, -120)
    assert view(page)["w"] != pytest.approx(framed["w"])

    page.get_by_test_id("zoom-fit").click()
    assert view(page)["w"] == pytest.approx(framed["w"], abs=0.01)
    expect(page.get_by_test_id("zoom-level")).to_have_text("100%")


def test_opening_another_diagram_frames_it(page: Page, server: str):
    """A view carried over from the previous diagram would open on empty space."""
    open_diagram(page, server, EX2)
    wheel(page, -120)
    wheel(page, -120)

    page.locator(f"[data-diagram-path='{EX1}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()
    expect(page.get_by_test_id("zoom-level")).to_have_text("100%")
    v = view(page)
    assert v["x"] <= 40 and v["w"] > 400


# ----- keyboard --------------------------------------------------------------------


def test_keyboard_zoom_shortcuts(page: Page, server: str):
    open_diagram(page, server)
    before = view(page)
    page.keyboard.press("+")
    assert view(page)["w"] < before["w"]
    page.keyboard.press("0")
    assert view(page)["w"] == pytest.approx(before["w"], abs=0.01)


def test_typing_in_a_field_does_not_zoom(page: Page, server: str):
    """`-` and `0` are ordinary characters in a parameter box."""
    open_diagram(page, server)
    before = view(page)
    page.locator(".node[data-block='force']").click()
    field = page.locator("[data-param='omega']")
    field.click()
    field.type("-0")
    assert view(page)["w"] == pytest.approx(before["w"], abs=0.01)
