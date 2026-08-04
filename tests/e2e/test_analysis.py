"""Browser tests for the linear-analysis charts: Bode and the pole-zero map.

The arithmetic behind these is pinned in `tests/unit/test_analysis.py` and the
payload in `tests/api/test_api.py`; what is only checkable here is the drawing —
in particular that a marker on the s-plane is attributed to the channel it
actually belongs to, which is where the two charts used to disagree.
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


def run(page: Page, t_max: str = "10", dt: str = "0.005") -> None:
    page.get_by_test_id("t-max").fill(t_max)
    page.get_by_test_id("dt").fill(dt)
    page.get_by_test_id("run").click()
    expect(page.get_by_test_id("run-status")).to_contain_text("samples", timeout=30_000)


def stroke_of(page: Page, selector: str) -> str:
    return page.locator(selector).first.get_attribute("stroke")


# ----- the panel appears with a run ---------------------------------------------


def test_a_run_draws_both_charts(page: Page, server: str):
    open_diagram(page, server)
    expect(page.get_by_test_id("analysis")).to_be_hidden()
    run(page)

    expect(page.get_by_test_id("analysis")).to_be_visible()
    expect(page.get_by_test_id("bode")).to_be_visible()
    expect(page.get_by_test_id("pzmap")).to_be_visible()
    expect(page.get_by_test_id("analysis-note")).to_be_hidden()


def test_the_bode_plot_draws_one_curve_per_channel_per_panel(page: Page, server: str):
    """Two outputs, one input, and two stacked panels -> four paths."""
    open_diagram(page, server)
    run(page)
    assert page.locator("#bode path[data-channel='plant.y[0]']").count() == 2
    assert page.locator("#bode path[data-channel='plant.y[1]']").count() == 2


def test_the_pole_zero_map_draws_the_plant_poles(page: Page, server: str):
    """A 2-state SDOF plant has two poles, and they belong to the system."""
    open_diagram(page, server)
    run(page)
    expect(page.locator("#pzmap [data-pole='plant']")).to_have_count(2)


# ----- the attribution the two charts used to get wrong ---------------------------


def test_a_zero_is_attributed_to_its_own_channel(page: Page, server: str):
    """`X/U = 1/(ms^2+cs+k)` has no zero; `X'/U = s/(ms^2+cs+k)` has one at the
    origin. Flattening both channels' zeros onto the system drew that zero as if
    it belonged to the position channel too."""
    open_diagram(page, server)
    run(page)
    expect(page.locator("#pzmap [data-zero='plant.y[1]']")).to_have_count(1)
    expect(page.locator("#pzmap [data-zero='plant.y[0]']")).to_have_count(0)


def test_a_channel_has_the_same_colour_in_both_charts(page: Page, server: str):
    """A colour has to mean the same channel on the s-plane as on the Bode plot,
    or the velocity zero reads as the position curve's."""
    open_diagram(page, server)
    run(page)
    bode = stroke_of(page, "#bode path[data-channel='plant.y[1]']")
    pz = stroke_of(page, "#pzmap [data-zero='plant.y[1]']")
    assert bode == pz, f"velocity is {bode} on the Bode plot but {pz} on the s-plane"

    # ...and distinct from the other channel, or the match would be vacuous
    assert bode != stroke_of(page, "#bode path[data-channel='plant.y[0]']")


# ----- a diagram with nothing to analyse ------------------------------------------


def test_a_nonlinear_plant_gets_an_explanation_not_an_empty_chart(
    page: Page, server: str
):
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    expect(page.get_by_test_id("analysis")).to_be_visible()
    expect(page.get_by_test_id("analysis-note")).to_be_visible()
    expect(page.get_by_test_id("analysis-note")).to_contain_text("no linear")


def test_opening_another_diagram_clears_the_analysis(page: Page, server: str):
    open_diagram(page, server)
    run(page)
    expect(page.get_by_test_id("bode")).to_be_visible()

    page.locator(f"[data-diagram-path='{EX1}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()
    expect(page.get_by_test_id("analysis")).to_be_hidden()
