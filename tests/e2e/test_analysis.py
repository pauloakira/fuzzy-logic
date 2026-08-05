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


def test_a_nonlinear_plant_is_linearized_and_labelled_as_such(page: Page, server: str):
    """`MotorPlant` has no (A,B,C,D) of its own; it is linearized, and the charts
    have to say so or they read as the plant itself."""
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    expect(page.get_by_test_id("analysis")).to_be_visible()
    expect(page.get_by_test_id("bode")).to_be_visible()
    expect(page.get_by_test_id("analysis-warnings")).to_contain_text("is nonlinear")


def test_linearizing_on_a_limit_is_said_out_loud(page: Page, server: str):
    """The motor's *initial* state (0 rpm, 0 V) is both lower clamps at once. The
    Bode plot drawn there looks perfectly reasonable and describes a corner, so
    the only thing between the reader and a wrong conclusion is this warning."""
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    page.get_by_test_id("op-point").select_option("initial")
    expect(page.get_by_test_id("analysis-warnings")).to_contain_text(
        "not differentiable"
    )


def test_an_lti_plant_carries_no_linearization_caveats(page: Page, server: str):
    """The SDOF plant is exactly linear, so there is nothing to warn about and a
    warning would train the reader to ignore them."""
    open_diagram(page, server, EX2)
    run(page)
    expect(page.get_by_test_id("analysis-warnings").locator("li")).to_have_count(0)


def test_opening_another_diagram_clears_the_analysis(page: Page, server: str):
    open_diagram(page, server)
    run(page)
    expect(page.get_by_test_id("bode")).to_be_visible()

    page.locator(f"[data-diagram-path='{EX1}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()
    expect(page.get_by_test_id("analysis")).to_be_hidden()


# ----- choosing where to linearize -------------------------------------------------


def mag_top(page: Page) -> float:
    """The top magnitude gridline label, which tracks the model's overall gain."""
    return float(page.evaluate(
        "() => Math.max(...window.__lastAnalysis.systems"
        ".flatMap(s => s.channels).flatMap(c => c.mag_db.filter(Number.isFinite)))"
    ))


def test_the_default_operating_point_is_the_end_of_the_run(page: Page, server: str):
    """`t = 0` puts the motor on both its lower clamps, where every Jacobian
    entry is corner-averaged to half — 18 dB of error on a plausible-looking
    plot. The settled state is free and is where the model is exact."""
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    expect(page.get_by_test_id("op-point")).to_have_value("run")
    expect(page.get_by_test_id("analysis-warnings")).not_to_contain_text(
        "not differentiable"
    )
    settled = mag_top(page)

    page.get_by_test_id("op-point").select_option("initial")
    expect(page.get_by_test_id("analysis-warnings")).to_contain_text(
        "not differentiable"
    )
    # halved A, B and C compound to 1/8 on the omega channel
    assert settled - mag_top(page) == pytest.approx(20 * 0.9031, abs=0.1)


def test_the_picker_is_hidden_when_nothing_is_linearized(page: Page, server: str):
    """The SDOF plant is exactly linear; an operating point is meaningless."""
    open_diagram(page, server, EX2)
    run(page)
    expect(page.get_by_test_id("op-point")).to_be_hidden()


def test_a_typed_state_is_used(page: Page, server: str):
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    page.get_by_test_id("op-point").select_option("custom")
    field = page.locator("[data-op-state='plant']")
    expect(field).to_be_visible()

    field.fill("0, 0")           # back onto both clamps, by hand
    field.blur()
    expect(page.get_by_test_id("analysis-warnings")).to_contain_text(
        "not differentiable"
    )


def test_a_malformed_typed_state_is_refused_not_guessed(page: Page, server: str):
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    page.get_by_test_id("op-point").select_option("custom")
    field = page.locator("[data-op-state='plant']")
    field.fill("500")            # one number for a two-state block
    field.blur()
    expect(field).to_have_attribute("data-invalid", "")
