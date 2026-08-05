"""Browser end-to-end tests for the editor page.

These assert on `data-testid` hooks rather than markup structure, so restyling
the page does not break them — only changing what it *means* does.

Scope note: this covers the thin page that exists today (palette, diagram list,
validation summary). The canvas arrives in step 7c and its tests belong here too.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

EX2 = "exercises/exercicio2_sdof_vibration_control/diagram.json"


@pytest.fixture(autouse=True)
def _no_console_errors(page_errors):
    """Every test in this module fails on an uncaught page error."""
    yield
    assert page_errors == [], f"page reported errors: {page_errors}"


def test_page_loads_and_reaches_ready(page: Page, server: str):
    page.goto(server)
    status = page.get_by_test_id("status")
    expect(status).to_have_attribute("data-ready", "true", timeout=10_000)
    expect(status).to_contain_text("block types")


def test_palette_is_populated_from_the_api(page: Page, server: str):
    """The page must render what /api/palette returns, not a hardcoded list."""
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    palette = page.get_by_test_id("palette").locator("li")
    # every registered block type, whatever that count happens to be
    registered = len(page.evaluate("() => Object.keys(window.__palette || {})") or [])
    expect(palette).to_have_count(registered or 14)
    expect(page.locator("[data-block-type='FISBlock']")).to_be_visible()
    expect(page.locator("[data-block-type='Observer']")).to_contain_text(
        "A, B, C, L, x0"
    )


def test_required_parameters_are_marked(page: Page, server: str):
    page.goto(server)
    expect(page.locator("[data-block-type='PIDBlock']")).to_contain_text(
        "required: kp, ki, kd"
    )


def test_both_committed_diagrams_are_offered(page: Page, server: str):
    page.goto(server)
    buttons = page.get_by_test_id("diagrams").locator("button")
    expect(buttons).to_have_count(2)
    expect(page.locator(f"[data-diagram-path='{EX2}']")).to_be_visible()


def test_opening_a_diagram_shows_its_shape_and_validity(page: Page, server: str):
    page.goto(server)
    page.locator(f"[data-diagram-path='{EX2}']").click()

    expect(page.get_by_test_id("summary")).to_be_visible()
    expect(page.get_by_test_id("block-count")).to_have_text("7")
    expect(page.get_by_test_id("connection-count")).to_have_text("8")
    expect(page.get_by_test_id("state-count")).to_have_text("2")
    expect(page.get_by_test_id("validity")).to_have_attribute("data-ok", "true")


def test_advice_from_the_api_reaches_the_screen(page: Page, server: str):
    """The stability limit and settling time are the most useful things shown."""
    page.goto(server)
    page.locator(f"[data-diagram-path='{EX2}']").click()
    advice = page.get_by_test_id("advice")
    expect(advice).to_contain_text("RK4 stability limit")
    expect(advice).to_contain_text("slowest time constant")


def test_loaded_spec_round_trips_into_the_browser(page: Page, server: str):
    """What the page holds must be the same document the simulator would build."""
    page.goto(server)
    page.locator(f"[data-diagram-path='{EX2}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()

    spec = page.evaluate("() => window.__lastSpec")
    assert spec["name"] == "ex2_sdof_fuzzy"
    names = [b["name"] for b in spec["blocks"]]
    assert {"plant", "controller", "actuator", "force"} <= set(names)
    # layout survives the trip, which is what the canvas will position from
    plant = next(b for b in spec["blocks"] if b["name"] == "plant")
    assert plant["layout"] == {"x": 360.0, "y": 120.0}
    # and the controller is fully described — no $provide placeholder
    controller = next(b for b in spec["blocks"] if b["name"] == "controller")
    assert len(controller["params"]["fis"]["rules"]) == 25


def test_page_is_usable_on_a_narrow_viewport(page: Page, server: str):
    page.set_viewport_size({"width": 380, "height": 800})
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    expect(page.get_by_test_id("palette")).to_be_visible()
    # no horizontal overflow
    overflow = page.evaluate(
        "() => { const d = document.documentElement;"
        "        return d.scrollWidth - d.clientWidth; }"
    )
    assert overflow <= 0


def test_the_open_diagram_is_marked_in_the_browser_list(page: Page, server: str):
    """Two rows that look identical give no clue which model is on the canvas."""
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    page.locator(
        "[data-diagram-path='exercises/exercicio2_sdof_vibration_control/diagram.json']"
    ).click()
    expect(page.get_by_test_id("summary")).to_be_visible()

    current = page.locator("[data-diagram-path][aria-current]")
    expect(current).to_have_count(1)
    expect(current).to_have_attribute(
        "data-diagram-path",
        "exercises/exercicio2_sdof_vibration_control/diagram.json",
    )


def test_the_status_bar_reports_the_model(page: Page, server: str):
    page.goto(server)
    expect(page.get_by_test_id("statusbar")).to_be_hidden()
    page.locator(
        "[data-diagram-path='exercises/exercicio2_sdof_vibration_control/diagram.json']"
    ).click()
    expect(page.get_by_test_id("statusbar")).to_be_visible()
    expect(page.get_by_test_id("status-shape")).to_contain_text("7 blocks")
    expect(page.get_by_test_id("status-validity")).to_have_attribute(
        "data-valid", "true"
    )
