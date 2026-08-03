"""Browser tests for running a simulation and plotting it (step 7e).

Exit criterion from the design note: click Run, see the response curve for the
edited diagram. The interesting part is the last clause — an edit made on the
canvas must be what gets simulated.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

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


def run(page: Page, t_max: str = "40", dt: str = "0.005") -> None:
    page.get_by_test_id("t-max").fill(t_max)
    page.get_by_test_id("dt").fill(dt)
    page.get_by_test_id("run").click()
    expect(page.get_by_test_id("run-status")).to_contain_text("samples", timeout=30_000)


def result(page: Page) -> dict:
    return page.evaluate("() => window.__lastResult")


# ----- running ------------------------------------------------------------------


def test_run_produces_a_plot(page: Page, server: str):
    open_diagram(page, server)
    expect(page.get_by_test_id("results")).to_be_hidden()
    run(page)

    expect(page.get_by_test_id("results")).to_be_visible()
    assert int(page.get_by_test_id("plot").get_attribute("data-series-count")) >= 1
    assert page.locator("#plot path[data-series]").count() >= 1


def test_default_signals_are_the_ones_worth_seeing(page: Page, server: str):
    """Plant states and the control command, not every intermediate wire."""
    open_diagram(page, server)
    run(page)
    drawn = page.eval_on_selector_all(
        "#plot path[data-series]", "els => els.map(e => e.dataset.series)"
    )
    assert "plant.y[0]" in drawn
    assert any(k in drawn for k in ("actuator.y", "controller.u"))


def test_every_signal_is_offered_as_a_toggle(page: Page, server: str):
    open_diagram(page, server)
    run(page)
    available = sorted(result(page)["signals"].keys())
    toggles = page.eval_on_selector_all(
        "[data-signal-toggle]", "els => els.map(e => e.dataset.signalToggle).sort()"
    )
    assert toggles == available


def test_toggling_a_signal_redraws_the_plot(page: Page, server: str):
    open_diagram(page, server)
    run(page)
    before = page.locator("#plot path[data-series]").count()
    page.locator("[data-signal-toggle='force.y']").check()
    expect(page.locator("#plot path[data-series]")).to_have_count(before + 1)
    assert page.locator("#plot path[data-series='force.y']").count() == 1


def test_the_run_is_decimated_for_the_plot(page: Page, server: str):
    """8001 samples per signal is megabytes of JSON a plot cannot resolve."""
    open_diagram(page, server)
    run(page)
    body = result(page)
    assert body["n_samples"] == 8001
    assert body["returned"] < body["n_samples"]
    assert len(body["t"]) == body["returned"]


def test_a_shorter_horizon_runs_fewer_samples(page: Page, server: str):
    open_diagram(page, server)
    run(page, t_max="5")
    assert result(page)["n_samples"] == 1001


# ----- warnings -----------------------------------------------------------------


def test_the_stability_guard_reaches_the_screen(page: Page, server: str):
    """An unstable step overflows silently; the warning is the only signal."""
    open_diagram(page, server)
    run(page, t_max="5", dt="0.35")
    expect(page.get_by_test_id("run-warnings")).to_contain_text(
        "exceeds the RK4 stability limit"
    )


def test_a_settled_run_reports_no_warnings(page: Page, server: str):
    open_diagram(page, server)
    run(page)
    expect(page.get_by_test_id("run-warnings").locator("li")).to_have_count(0)


# ----- editing and running together ---------------------------------------------


def test_an_edit_on_the_canvas_is_what_gets_simulated(page: Page, server: str):
    """The exit criterion's real content: the plot follows the edited diagram."""
    open_diagram(page, server)
    run(page, t_max="20")
    before = max(abs(v) for v in result(page)["signals"]["plant.y[0]"])

    # Detune the controller by shrinking its output, then run the same horizon.
    page.locator(".node[data-block='controller']").click()
    field = page.locator("[data-param='output_gain']")
    field.fill("0")
    field.blur()
    run(page, t_max="20")
    after = max(abs(v) for v in result(page)["signals"]["plant.y[0]"])

    # With the controller silenced the plant is open loop, so it swings further.
    assert after > before * 1.5


def test_deleting_the_controller_and_running_still_works(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='controller']").click()
    page.get_by_test_id("delete-selected").click()
    page.locator(".node[data-block='actuator']").click()
    page.get_by_test_id("delete-selected").click()
    # `total.ctrl` is now unwired, so the diagram cannot run.
    page.get_by_test_id("run").click()
    expect(page.get_by_test_id("run-status")).to_have_text("failed")
    expect(page.get_by_test_id("run-warnings")).to_contain_text("not connected")


def test_opening_another_diagram_clears_the_previous_result(page: Page, server: str):
    open_diagram(page, server)
    run(page, t_max="5")
    expect(page.get_by_test_id("results")).to_be_visible()
    page.locator(
        "[data-diagram-path='exercises/exercicio1_motor_control/diagram.json']"
    ).click()
    expect(page.get_by_test_id("results")).to_be_hidden()


def test_exercise_one_runs_too(page: Page, server: str):
    open_diagram(page, server, "exercises/exercicio1_motor_control/diagram.json")
    run(page, t_max="800", dt="1")
    body = result(page)
    assert body["n_samples"] == 801
    # the motor settles towards its (500 rpm, 50 V) fixed point, slowly
    assert 400 < body["signals"]["plant.y[0]"][-1] < 700
