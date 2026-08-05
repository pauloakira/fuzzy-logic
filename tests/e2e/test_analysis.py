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
    """Run, then wait for the *analysis* — not the run status.

    `/api/simulate` returning is not `/api/analyze` returning: the run status
    says "N samples" before the analysis fetch has even started, so waiting on it
    reads the charts a beat early. It passed until the loop grid got denser.
    """
    page.get_by_test_id("t-max").fill(t_max)
    page.get_by_test_id("dt").fill(dt)
    page.get_by_test_id("run").click()
    expect(page.get_by_test_id("run-status")).to_contain_text("samples", timeout=30_000)
    expect(page.get_by_test_id("analysis")).to_have_attribute(
        "data-ready", "true", timeout=30_000
    )


def set_op_mode(page: Page, value: str) -> None:
    """Change where to linearize, and wait for the re-analysis it kicks off.

    The select fires an async `/api/analyze`; reading the charts straight after
    `select_option` reads the previous ones.
    """
    page.get_by_test_id("analysis").evaluate("e => e.dataset.ready = 'false'")
    page.get_by_test_id("op-point").select_option(value)
    expect(page.get_by_test_id("analysis")).to_have_attribute(
        "data-ready", "true", timeout=30_000
    )


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
    set_op_mode(page, "initial")
    expect(page.get_by_test_id("analysis-warnings")).to_contain_text(
        "not differentiable"
    )


def test_an_lti_plant_block_carries_no_caveats_but_its_loop_does(
    page: Page, server: str
):
    """The SDOF plant is exactly linear. The loop around it is not — it contains a
    sampled fuzzy controller and a saturation — so the block-level model is exact
    while the closed-loop one rests on the fast-sampling approximation."""
    open_diagram(page, server, EX2)
    run(page)
    systems = page.evaluate("() => window.__lastAnalysis.systems")
    block = next(s for s in systems if s["kind"] == "block")
    loop = next(s for s in systems if s["kind"] == "diagram")
    assert block["warnings"] == []
    assert block["linearized"] is False
    assert any("sampling delay" in w for w in loop["warnings"])


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
        ".filter(s => s.kind === 'block')"
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

    set_op_mode(page, "initial")
    expect(page.get_by_test_id("analysis-warnings")).to_contain_text(
        "not differentiable"
    )
    # halved A, B and C compound to 1/8 on the omega channel
    assert settled - mag_top(page) == pytest.approx(20 * 0.9031, abs=0.1)


def test_the_custom_editor_offers_blocks_not_the_synthetic_diagram_entry(
    page: Page, server: str
):
    """A hand-typed per-block state cannot be composed into the diagram's own
    state vector without knowing its layout, so offering a row for the closed
    loop would promise something the picker cannot deliver."""
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    set_op_mode(page, "custom")
    rows = page.eval_on_selector_all(
        "[data-op-state]", "els => els.map(e => e.dataset.opState)"
    )
    assert rows == ["plant"]


def test_a_typed_state_is_used(page: Page, server: str):
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    set_op_mode(page, "custom")
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
    set_op_mode(page, "custom")
    field = page.locator("[data-op-state='plant']")
    field.fill("500")            # one number for a two-state block
    field.blur()
    expect(field).to_have_attribute("data-invalid", "")


def test_the_closed_loop_is_charted_beside_the_bare_plant(page: Page, server: str):
    """The comparison that matters: the fuzzy controller more than quadruples the
    damping, and you can only see that with both pole sets on one map."""
    open_diagram(page, server, EX2)
    run(page)
    systems = page.evaluate("() => window.__lastAnalysis.systems")
    kinds = {s["kind"]: s for s in systems}
    assert set(kinds) == {"diagram", "block", "loop"}

    def zeta(s):
        re, im = s["poles"][0]
        return -re / (re**2 + im**2) ** 0.5

    assert zeta(kinds["block"]) == pytest.approx(0.02, abs=1e-3)
    assert zeta(kinds["diagram"]) > 0.08

    # both pole sets are on the map, and told apart by colour
    assert page.locator("#pzmap [data-pole]").count() == 4
    strokes = page.eval_on_selector_all(
        "#pzmap [data-pole]",
        "els => [...new Set(els.map(e => e.getAttribute('stroke')))]",
    )
    assert len(strokes) == 2


def test_the_stability_margins_are_reported_as_numbers(page: Page, server: str):
    """A margin is a number, not a shape; reading it off a curve by eye is what
    the chart cannot do."""
    open_diagram(page, server, EX2)
    run(page)
    expect(page.get_by_test_id("margins")).to_be_visible()
    expect(page.get_by_test_id("margins")).to_contain_text("Loop broken at total.y")
    expect(page.get_by_test_id("margins")).to_contain_text("phase margin")

    # The exact value moves with the operating point — that is the feature, not
    # a flake — so the browser pins the shape and `test_linearize.py` the number.
    pm = page.evaluate(
        "() => window.__lastAnalysis.systems.find(s => s.kind === 'loop')"
        ".margins.phase_margin_deg"
    )
    assert 30.0 < pm < 90.0, f"implausible phase margin {pm}"


def test_a_missing_margin_says_so_rather_than_inventing_one(page: Page, server: str):
    """This loop's phase approaches -180 deg without reaching it, so there is no
    gain margin to quote."""
    open_diagram(page, server, EX2)
    run(page)
    expect(page.get_by_test_id("margins")).to_contain_text("never reaches")


def test_the_open_loop_is_not_redrawn_on_the_s_plane(page: Page, server: str):
    """`L(s)`'s poles are the plant's own — cutting the loop is what makes them
    so — and two colours at identical points would read as two pole sets."""
    open_diagram(page, server, EX2)
    run(page)
    names = page.eval_on_selector_all(
        "#pzmap [data-pole]", "els => [...new Set(els.map(e => e.dataset.pole))]"
    )
    assert not any("L(s)" in n for n in names)
    assert len(names) == 2  # the plant block and the closed loop


# ----- Nyquist and root locus -----------------------------------------------------


def test_the_nyquist_plot_draws_both_halves_and_the_critical_point(
    page: Page, server: str
):
    """A Nyquist plot without the -1 marked is just a curve; the mirror for
    negative omega is what closes the contour and makes an encirclement
    countable."""
    open_diagram(page, server, EX2)
    run(page)
    expect(page.locator("#nyquist [data-nyquist='positive']")).to_have_count(1)
    expect(page.locator("#nyquist [data-nyquist='negative']")).to_have_count(1)
    expect(page.locator("#nyquist [data-critical='-1']")).to_have_count(1)


def test_the_root_locus_marks_where_it_starts_and_where_the_loop_sits(
    page: Page, server: str
):
    """One branch per state, each starting at an open-loop pole, with the design
    gain marked — a locus that does not say which point is the built loop leaves
    the reader guessing."""
    open_diagram(page, server, EX2)
    run(page)
    assert page.locator("#locus [data-branch]").count() == 2
    assert page.locator("#locus [data-locus-start]").count() == 2
    assert page.locator("#locus [data-locus-design]").count() == 2


def test_the_locus_design_marker_sits_on_the_closed_loop_poles(page: Page, server: str):
    """k = 1 is the loop as actually built, so its marker must land exactly on
    the poles the closed-loop model reports."""
    open_diagram(page, server, EX2)
    run(page)
    drawn = page.evaluate(
        "() => { const s = window.__lastAnalysis.systems;"
        " const loop = s.find(x => x.kind === 'loop');"
        " const g = loop.locus.gains;"
        " let i = 0;"
        " g.forEach((v, j) => { if (Math.abs(v-1) < Math.abs(g[i]-1)) i = j; });"
        " return loop.locus.branches.map(b => b[i]); }"
    )
    closed = page.evaluate(
        "() => window.__lastAnalysis.systems.find(x => x.kind === 'diagram').poles"
    )
    for (re, im), (want_re, want_im) in zip(sorted(drawn), sorted(closed), strict=True):
        assert re == pytest.approx(want_re, abs=1e-6)
        assert im == pytest.approx(want_im, abs=1e-6)


def test_the_loop_charts_are_hidden_without_a_loop(page: Page, server: str):
    """Exercise 1's motor has no feedback path around it to break."""
    open_diagram(page, server, EX1)
    run(page, t_max="800", dt="1")
    if page.evaluate("() => !window.__lastAnalysis.systems.some(s => s.kind==='loop')"):
        expect(page.get_by_test_id("nyquist")).to_be_hidden()


def test_the_complex_plane_charts_clip_to_their_own_box(page: Page, server: str):
    """The view is scaled to a percentile, so part of the curve is outside it by
    construction — a locus near a pole runs to infinity. SVG does not clip on its
    own, and the overflow paints over whatever sits next to the chart."""
    open_diagram(page, server, EX2)
    run(page)
    for sel in ("#nyquist [data-nyquist='positive']", "#locus [data-branch='0']"):
        clipped = page.eval_on_selector(sel, "e => e.getAttribute('clip-path')")
        assert clipped and clipped.startswith("url(#"), f"{sel} is not clipped"
    assert page.locator("#nyquist clipPath").count() == 1
    assert page.locator("#locus clipPath").count() == 1
