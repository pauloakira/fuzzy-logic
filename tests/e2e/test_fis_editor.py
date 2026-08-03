"""Browser tests for the fuzzy controller editor (step 7f).

Exit criterion from the design note: drag membership-function breakpoints, edit
the rule grid, and watch the control surface change.

This is the step the declarative-FIS work in phase 4 was for. A term used to be a
Python closure; because it is data, it can be dragged.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

EX2 = "exercises/exercicio2_sdof_vibration_control/diagram.json"


@pytest.fixture(autouse=True)
def _no_console_errors(page_errors):
    yield
    assert page_errors == [], f"page reported errors: {page_errors}"


def open_controller(page: Page, server: str) -> None:
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    page.locator(f"[data-diagram-path='{EX2}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()
    page.locator(".node[data-block='controller']").click()
    expect(page.get_by_test_id("fis-editor")).to_be_visible()
    expect(page.locator("[data-testid='fis-surface']")).to_be_visible()


def preview(page: Page) -> dict:
    return page.evaluate("() => window.__lastPreview")


def surface_extent(page: Page) -> float:
    return float(page.locator(".surface").get_attribute("data-extent"))


def fis_of(page: Page) -> dict:
    return page.evaluate(
        "() => window.__lastSpec.blocks.find(b => b.name === 'controller').params.fis"
    )


# ----- it opens for a FISBlock and only a FISBlock -------------------------------


def test_selecting_the_controller_opens_the_editor(page: Page, server: str):
    open_controller(page, server)
    expect(page.get_by_test_id("fis-block-name")).to_have_text("controller")


def test_selecting_an_ordinary_block_closes_it(page: Page, server: str):
    open_controller(page, server)
    page.locator(".node[data-block='plant']").click()
    expect(page.get_by_test_id("fis-editor")).to_be_hidden()


# ----- membership functions -----------------------------------------------------


def test_every_variable_gets_a_membership_plot(page: Page, server: str):
    open_controller(page, server)
    drawn = page.eval_on_selector_all(
        "[data-variable]", "els => els.map(e => e.dataset.variable)"
    )
    assert drawn == ["deslocamento", "velocidade", "__output__"]


def test_each_plot_draws_one_curve_per_term(page: Page, server: str):
    open_controller(page, server)
    curves = page.locator("[data-variable='deslocamento'] .mf-curve")
    expect(curves).to_have_count(5)
    names = page.eval_on_selector_all(
        "[data-variable='deslocamento'] .mf-curve",
        "els => els.map(e => e.dataset.term)",
    )
    assert names == ["NG", "NP", "Z", "PP", "PG"]


def test_breakpoints_are_draggable_handles(page: Page, server: str):
    """Shoulders have two parameters, triangles three: 2+3+3+3+2 = 13 per variable."""
    open_controller(page, server)
    handles = page.locator("[data-variable='deslocamento'] .mf-handle")
    expect(handles).to_have_count(13)
    expect(page.locator("[data-handle='deslocamento.Z.1']")).to_have_count(1)


def drag_handle(page: Page, handle_id: str, dx: int) -> None:
    """Drag a breakpoint horizontally.

    `mouse.move` takes viewport coordinates and does not scroll, so the handle
    has to be brought into view before its box is read.
    """
    handle = page.locator(f"[data-handle='{handle_id}']")
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + dx, cy, steps=8)
    page.mouse.up()


def surface_values(page: Page) -> list:
    """The surface itself, flattened.

    `data-extent` is max|z|, which a *local* change — one rule, one breakpoint —
    leaves untouched, so comparing extents would pass a broken editor.
    """
    return page.evaluate("() => window.__lastPreview.surface.z.flat()")


def revision(page: Page) -> str:
    return page.get_by_test_id("fis-editor").get_attribute("data-revision")


def await_redraw(page: Page, previous: str) -> None:
    """The preview is fetched from the server, so a redraw is asynchronous."""
    expect(page.get_by_test_id("fis-editor")).not_to_have_attribute(
        "data-revision", previous
    )


def test_dragging_a_breakpoint_changes_the_term(page: Page, server: str):
    open_controller(page, server)
    before = fis_of(page)["inputs"]["deslocamento"]["terms"]["Z"]["params"]

    drag_handle(page, "deslocamento.Z.1", 25)

    after = fis_of(page)["inputs"]["deslocamento"]["terms"]["Z"]["params"]
    assert after != before
    assert after[1] > before[1]  # the peak moved right
    expect(page.get_by_test_id("dirty")).to_be_visible()


def test_dragging_a_breakpoint_changes_the_control_surface(page: Page, server: str):
    """The exit criterion: the surface responds to a dragged breakpoint."""
    open_controller(page, server)
    before, rev = surface_values(page), revision(page)

    # Widening the PG output shoulder shifts its centroid, so the command changes.
    drag_handle(page, "__output__.PG.0", -40)
    await_redraw(page, rev)

    after = surface_values(page)
    assert after != before
    assert max(abs(a - b) for a, b in zip(after, before, strict=True)) > 1e-3


def test_a_drag_cannot_push_a_breakpoint_past_its_neighbour(page: Page, server: str):
    """`Term` rejects out-of-order parameters, so the drag clamps instead."""
    open_controller(page, server)
    drag_handle(page, "deslocamento.Z.0", 400)

    params = fis_of(page)["inputs"]["deslocamento"]["terms"]["Z"]["params"]
    assert params == sorted(params), "parameters must stay ordered"
    assert preview(page)["problems"] == [] or all(
        "not a strong partition" in p for p in preview(page)["problems"]
    )


# ----- rules ---------------------------------------------------------------------


def test_the_rule_base_is_shown_as_a_grid(page: Page, server: str):
    open_controller(page, server)
    expect(page.locator("[data-rule]")).to_have_count(25)
    expect(page.locator("[data-rule='NG|NG']")).to_have_value("PG")
    expect(page.locator("[data-rule='PG|PG']")).to_have_value("NG")


def test_changing_a_rule_cell_updates_the_spec(page: Page, server: str):
    open_controller(page, server)
    page.locator("[data-rule='Z|Z']").select_option("PG")

    rules = fis_of(page)["rules"]
    match = next(
        r for r in rules
        if r["if"] == {"deslocamento": "Z", "velocidade": "Z"}
    )
    assert match["then"] == "PG"
    expect(page.get_by_test_id("dirty")).to_be_visible()


def test_changing_a_rule_changes_the_control_surface(page: Page, server: str):
    open_controller(page, server)
    before, rev = surface_values(page), revision(page)
    # (Z, Z) commands nothing; making it push hard changes the surface near the
    # origin — which `data-extent` (max|z|, set by the corners) would not show.
    page.locator("[data-rule='Z|Z']").select_option("PG")
    await_redraw(page, rev)
    assert surface_values(page) != before


def test_clearing_a_rule_cell_removes_the_rule_and_is_reported(page: Page, server: str):
    open_controller(page, server)
    rev = revision(page)
    page.locator("[data-rule='NG|NG']").select_option("")
    await_redraw(page, rev)

    assert len(fis_of(page)["rules"]) == 24
    expect(page.get_by_test_id("fis-problems")).to_contain_text("96%")


def test_a_removed_rule_leaves_its_cell_marked(page: Page, server: str):
    open_controller(page, server)
    page.locator("[data-rule='NG|NG']").select_option("")
    expect(page.locator("td.missing")).to_have_count(1)


# ----- surface --------------------------------------------------------------------


def test_the_control_surface_is_drawn_over_both_inputs(page: Page, server: str):
    open_controller(page, server)
    expect(page.locator("[data-cell]")).to_have_count(625)
    body = preview(page)
    assert body["surface"]["axes"] == ["deslocamento", "velocidade"]


def test_the_surface_matches_the_documented_centroid_ceiling(page: Page, server: str):
    """REPORT.md §11: centroid defuzzification caps the command at +/-2.505 N."""
    open_controller(page, server)
    assert surface_extent(page) == pytest.approx(2.505, abs=1e-3)


# ----- the edit reaches the simulation ---------------------------------------------


def test_a_rule_edit_changes_the_simulated_response(page: Page, server: str):
    """A controller edited in the grid is the controller that runs."""
    open_controller(page, server)
    page.get_by_test_id("t-max").fill("20")
    page.get_by_test_id("run").click()
    expect(page.get_by_test_id("run-status")).to_contain_text("samples", timeout=30_000)
    before = page.evaluate(
        "() => Math.max(...window.__lastResult.signals['plant.y[0]'].map(Math.abs))"
    )

    # Invert the whole rule base: the controller now drives the plant instead of
    # opposing it, which must make the response worse.
    page.locator(".node[data-block='controller']").click()
    flip = {"NG": "PG", "NP": "PP", "Z": "Z", "PP": "NP", "PG": "NG"}
    for row in ("NG", "PG"):
        for col in ("NG", "PG"):
            cell = page.locator(f"[data-rule='{row}|{col}']")
            cell.select_option(flip[cell.input_value()])

    page.get_by_test_id("run").click()
    expect(page.get_by_test_id("run-status")).to_contain_text("samples", timeout=30_000)
    after = page.evaluate(
        "() => Math.max(...window.__lastResult.signals['plant.y[0]'].map(Math.abs))"
    )
    assert after > before
