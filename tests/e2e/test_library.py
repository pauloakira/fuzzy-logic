"""Browser tests for the block library panel.

It used to be a flat alphabetical list of names and parameters that looked like
a library browser and could not add anything — blocks came from a separate
dropdown in the toolbar. These pin the three things that changed: it is grouped,
it is searchable, and a row puts the block on the canvas.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

EX2 = "exercises/exercicio2_sdof_vibration_control/diagram.json"


@pytest.fixture(autouse=True)
def _no_console_errors(page_errors):
    yield
    assert page_errors == [], f"page reported errors: {page_errors}"


def open_editor(page: Page, server: str, path: str = EX2) -> None:
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    page.locator(f"[data-diagram-path='{path}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()


# ----- structure -------------------------------------------------------------


def test_blocks_are_grouped_by_library_section(page: Page, server: str):
    """The sections `blocks.py` already organises itself into, which the old
    alphabetical list threw away."""
    open_editor(page, server)
    groups = page.eval_on_selector_all(
        ".palette-group", "els => els.map(e => e.dataset.category)"
    )
    assert groups == ["Sources", "Math", "Plants", "Controllers"]


def test_a_row_draws_the_block_it_produces(page: Page, server: str):
    """The affordance the text list had none of: a palette row is a picture of
    what lands on the canvas, drawn through the same renderer."""
    open_editor(page, server)
    gain = page.locator(".palette-item[data-block-type='Gain']")
    # a gain is a triangle on the canvas, so it is a triangle here too
    expect(gain.locator("polygon.node-shape")).to_have_count(1)
    expect(
        page.locator(".palette-item[data-block-type='Sum'] circle.node-shape")
    ).to_have_count(1)


def test_every_registered_type_appears_exactly_once(page: Page, server: str):
    open_editor(page, server)
    rows = page.eval_on_selector_all(
        ".palette-item", "els => els.map(e => e.dataset.blockType)"
    )
    registered = list(page.evaluate("() => Object.keys(window.__palette)"))
    assert sorted(rows) == sorted(registered)


# ----- search ----------------------------------------------------------------


def test_the_filter_narrows_to_matching_blocks(page: Page, server: str):
    open_editor(page, server)
    page.get_by_test_id("palette-filter").fill("sat")
    rows = page.eval_on_selector_all(
        ".palette-item", "els => els.map(e => e.dataset.blockType)"
    )
    assert rows == ["Saturation"]


def test_the_filter_matches_parameter_names_too(page: Page, server: str):
    """Someone hunting for a saturation limit searches `hi`, not `Saturation`."""
    open_editor(page, server)
    page.get_by_test_id("palette-filter").fill("omega_rate_max")
    rows = page.eval_on_selector_all(
        ".palette-item", "els => els.map(e => e.dataset.blockType)"
    )
    assert rows == ["MotorPlant"]


def test_a_filter_matching_nothing_says_so(page: Page, server: str):
    open_editor(page, server)
    page.get_by_test_id("palette-filter").fill("zzzz")
    expect(page.locator(".palette-empty")).to_contain_text("No block matches")
    assert page.locator(".palette-item").count() == 0


# ----- the details pane ------------------------------------------------------


def test_selecting_a_block_shows_its_parameters(page: Page, server: str):
    """Parameters left the row because they made `MotorPlant` two lines tall and
    could not be acted on there."""
    open_editor(page, server)
    expect(page.get_by_test_id("palette-details")).to_be_hidden()

    page.locator(".palette-item[data-block-type='Saturation']").focus()
    expect(page.get_by_test_id("palette-details")).to_be_visible()
    expect(page.get_by_test_id("palette-detail-name")).to_have_text("Saturation")
    params = page.get_by_test_id("palette-detail-params")
    expect(params).to_contain_text("lo")
    expect(params).to_contain_text("hi")
    expect(params).to_contain_text("required")


# ----- adding ----------------------------------------------------------------


def test_clicking_a_row_adds_the_block(page: Page, server: str):
    open_editor(page, server)
    before = page.get_by_test_id("nodes").locator(".node").count()
    page.locator(".palette-item[data-block-type='Gain']").click()
    expect(page.get_by_test_id("nodes").locator(".node")).to_have_count(before + 1)
    expect(page.locator(".node[data-type='Gain']")).to_have_count(1)
    expect(page.get_by_test_id("dirty")).to_be_visible()


def test_a_row_can_be_dragged_onto_the_canvas_where_it_is_dropped(
    page: Page, server: str
):
    """Simulink's own gesture. The block lands where it was dropped rather than
    in the next free slot, which is the whole reason to drag rather than click."""
    open_editor(page, server)
    canvas = page.get_by_test_id("canvas")
    box = canvas.bounding_box()
    target = {"x": box["x"] + box["width"] * 0.35, "y": box["y"] + box["height"] * 0.7}

    # Playwright's mouse does not raise HTML5 drag events, so drive the transfer
    # directly. Doing both would add the block twice: a synthetic mousedown-move-up
    # on the row fires `click` as well, where a real `dragstart` suppresses it.
    page.evaluate(
        """([x, y]) => {
            const dt = new DataTransfer();
            dt.setData('text/block-type', 'Step');
            const svg = document.getElementById('canvas');
            const opts = {dataTransfer: dt, clientX: x, clientY: y,
                          bubbles: true, cancelable: true};
            svg.dispatchEvent(new DragEvent('dragover', opts));
            svg.dispatchEvent(new DragEvent('drop', opts));
        }""",
        [target["x"], target["y"]],
    )
    node = page.locator(".node[data-type='Step']")
    expect(node).to_have_count(1)

    # it landed near the drop, not at the default slot
    dropped = page.evaluate(
        """([x, y]) => {
            const svg = document.getElementById('canvas');
            const p = svg.createSVGPoint(); p.x = x; p.y = y;
            const q = p.matrixTransform(svg.getScreenCTM().inverse());
            return [q.x, q.y];
        }""",
        [target["x"], target["y"]],
    )
    assert abs(float(node.get_attribute("data-x")) - dropped[0]) < 80
    assert abs(float(node.get_attribute("data-y")) - dropped[1]) < 80


def test_the_canvas_signals_that_it_will_accept_the_drop(page: Page, server: str):
    open_editor(page, server)
    page.evaluate(
        """() => {
            const dt = new DataTransfer();
            dt.setData('text/block-type', 'Gain');
            document.getElementById('canvas').dispatchEvent(new DragEvent('dragover',
                {dataTransfer: dt, clientX: 300, clientY: 300,
                 bubbles: true, cancelable: true}));
        }"""
    )
    expect(page.get_by_test_id("canvas")).to_have_attribute("data-drop-target", "true")
