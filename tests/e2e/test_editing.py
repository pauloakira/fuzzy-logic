"""Browser tests for interactive editing (step 7d).

Exit criterion from the design note: drag a node, edit a parameter, add or remove
a block or wire, save — and the file on disk changes. Each of those is asserted
here, ending with reading the written file back.

The spec document is the source of truth, so every test checks what happened to
`window.__lastSpec` (or the saved file), not just what appeared on screen.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from editor.api import REPO_ROOT

EX2 = "exercises/exercicio2_sdof_vibration_control/diagram.json"
DRAFT = "exercises/exercicio2_sdof_vibration_control/diagram.draft.json"


@pytest.fixture(autouse=True)
def _no_console_errors(page_errors):
    yield
    assert page_errors == [], f"page reported errors: {page_errors}"


@pytest.fixture(autouse=True)
def _clean_draft():
    """Remove anything a test wrote, however it ended."""
    path = REPO_ROOT / DRAFT
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


def open_diagram(page: Page, server: str, path: str = EX2) -> None:
    page.goto(server)
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    page.locator(f"[data-diagram-path='{path}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()


def spec_of(page: Page) -> dict:
    return page.evaluate("() => window.__lastSpec")


def drag(page: Page, selector: str, dx: int, dy: int) -> None:
    box = page.locator(selector).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + dx, box["y"] + box["height"] / 2 + dy,
                    steps=8)
    page.mouse.up()


# ----- moving -----------------------------------------------------------------


def test_dragging_a_node_writes_its_new_position_into_the_spec(page: Page, server: str):
    open_diagram(page, server)
    before = next(b for b in spec_of(page)["blocks"] if b["name"] == "plant")
    assert before["layout"] == {"x": 360.0, "y": 120.0}

    drag(page, ".node[data-block='plant']", 60, -40)

    after = next(b for b in spec_of(page)["blocks"] if b["name"] == "plant")
    assert after["layout"]["x"] != 360.0 or after["layout"]["y"] != 120.0
    assert after["layout"]["y"] < before["layout"]["y"]  # dragged upwards


def test_dragging_marks_the_diagram_unsaved(page: Page, server: str):
    open_diagram(page, server)
    expect(page.get_by_test_id("dirty")).to_be_hidden()
    drag(page, ".node[data-block='plant']", 40, 30)
    expect(page.get_by_test_id("dirty")).to_be_visible()


def test_a_click_without_movement_selects_but_does_not_dirty(page: Page, server: str):
    """Click jitter must not count as a move, or every selection marks unsaved."""
    open_diagram(page, server)
    page.locator(".node[data-block='plant']").click()
    expect(page.get_by_test_id("selected-name")).to_have_text("plant")
    expect(page.get_by_test_id("dirty")).to_be_hidden()


def test_wires_follow_a_dragged_node(page: Page, server: str):
    open_diagram(page, server)
    wire = "[data-wire='total.y->plant.u']"
    before = page.locator(wire).get_attribute("d")
    drag(page, ".node[data-block='plant']", 70, 50)
    assert page.locator(wire).get_attribute("d") != before


# ----- parameters -------------------------------------------------------------


def test_editing_a_scalar_parameter_updates_the_spec(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='force']").click()
    field = page.locator("[data-param='omega']")
    field.fill("7.5")
    field.blur()

    force = next(b for b in spec_of(page)["blocks"] if b["name"] == "force")
    assert force["params"]["omega"] == 7.5
    expect(page.get_by_test_id("dirty")).to_be_visible()


def test_editing_a_matrix_parameter_updates_the_spec(page: Page, server: str):
    """Structured values are edited as JSON, which is honest about what they are."""
    open_diagram(page, server)
    page.locator(".node[data-block='plant']").click()
    field = page.locator("[data-param='A']")
    field.fill("[[0,1],[-400,-0.8]]")
    field.blur()

    plant = next(b for b in spec_of(page)["blocks"] if b["name"] == "plant")
    assert plant["params"]["A"] == [[0, 1], [-400, -0.8]]


def test_a_parameter_edit_revalidates_live(page: Page, server: str):
    """Stiffening the plant must move the reported stability limit."""
    open_diagram(page, server)
    before = page.get_by_test_id("advice").inner_text()
    page.locator(".node[data-block='plant']").click()
    field = page.locator("[data-param='A']")
    field.fill("[[0,1],[-10000,-0.4]]")
    field.blur()
    expect(page.get_by_test_id("advice")).not_to_have_text(before)
    assert "0.02828" in page.get_by_test_id("advice").inner_text()


def test_invalid_json_is_rejected_and_leaves_the_spec_alone(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='plant']").click()
    field = page.locator("[data-param='A']")
    field.fill("[[0,1],[oops")
    field.blur()

    expect(field).to_have_attribute("data-invalid", "true")
    plant = next(b for b in spec_of(page)["blocks"] if b["name"] == "plant")
    assert plant["params"]["A"] == [[0.0, 1.0], [-100.0, -0.4]]  # untouched


# ----- adding and removing ------------------------------------------------------


def test_adding_a_block_from_the_palette(page: Page, server: str):
    open_diagram(page, server)
    page.get_by_test_id("add-block").select_option("Gain")

    expect(page.get_by_test_id("canvas")).to_have_attribute("data-nodes", "8")
    expect(page.locator(".node[data-block='gain']")).to_have_count(1)
    added = next(b for b in spec_of(page)["blocks"] if b["name"] == "gain")
    assert added["type"] == "Gain"
    assert "layout" in added  # placed somewhere, not at the origin


def test_added_blocks_get_unique_names(page: Page, server: str):
    open_diagram(page, server)
    page.get_by_test_id("add-block").select_option("Gain")
    page.get_by_test_id("add-block").select_option("Gain")
    names = [b["name"] for b in spec_of(page)["blocks"]]
    assert "gain" in names and "gain2" in names


def test_an_added_block_is_reported_invalid_until_wired(page: Page, server: str):
    """A new block has an unconnected input; the canvas should say so and mark it."""
    open_diagram(page, server)
    page.get_by_test_id("add-block").select_option("Gain")
    expect(page.get_by_test_id("validity")).to_have_attribute("data-ok", "false")
    expect(page.locator(".node[data-block='gain'][data-problem]")).to_have_count(1)


def test_deleting_a_block_also_removes_its_wires(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='actuator']").click()
    page.get_by_test_id("delete-selected").click()

    spec = spec_of(page)
    assert "actuator" not in [b["name"] for b in spec["blocks"]]
    touching = [
        c for c in spec["connections"]
        if c["from"][0] == "actuator" or c["to"][0] == "actuator"
    ]
    assert touching == [], "a dangling wire would make the spec unloadable"


def test_deleting_a_wire_leaves_its_blocks(page: Page, server: str):
    open_diagram(page, server)
    page.locator("[data-wire='force.y->total.ext']").click()
    expect(page.get_by_test_id("selected-type")).to_have_text("connection")
    page.get_by_test_id("delete-selected").click()

    spec = spec_of(page)
    assert len(spec["connections"]) == 7
    assert {"force", "total"} <= {b["name"] for b in spec["blocks"]}


def test_delete_key_removes_the_selection(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='actuator']").click()
    page.keyboard.press("Delete")
    assert "actuator" not in [b["name"] for b in spec_of(page)["blocks"]]


def test_delete_is_disabled_with_nothing_selected(page: Page, server: str):
    open_diagram(page, server)
    expect(page.get_by_test_id("delete-selected")).to_be_disabled()


# ----- wiring -------------------------------------------------------------------


def test_dragging_between_ports_creates_a_wire(page: Page, server: str):
    open_diagram(page, server)
    page.locator("[data-wire='force.y->total.ext']").click()
    page.get_by_test_id("delete-selected").click()
    # Wait on the *render*, not the spec: `window.__lastSpec` updates before the
    # canvas is redrawn, so locating a port too early finds a detached element.
    expect(page.get_by_test_id("canvas")).to_have_attribute("data-wires", "7")
    assert len(spec_of(page)["connections"]) == 7

    src = page.locator("[data-port='force.y']").bounding_box()
    dst = page.locator("[data-port='total.ext']").bounding_box()
    page.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    page.mouse.down()
    page.mouse.move(dst["x"] + dst["width"] / 2, dst["y"] + dst["height"] / 2, steps=10)
    page.mouse.up()

    spec = spec_of(page)
    assert len(spec["connections"]) == 8
    assert {"from": ["force", "y"], "to": ["total", "ext"]} in [
        {"from": c["from"], "to": c["to"]} for c in spec["connections"]
    ]


def test_rewiring_an_input_replaces_the_existing_wire(page: Page, server: str):
    """An input takes one source; the second wire replaces the first."""
    open_diagram(page, server)
    expect(page.get_by_test_id("canvas")).to_have_attribute("data-wires", "8")
    src = page.locator("[data-port='pos.y']").bounding_box()
    dst = page.locator("[data-port='plant.u']").bounding_box()
    page.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    page.mouse.down()
    page.mouse.move(dst["x"] + dst["width"] / 2, dst["y"] + dst["height"] / 2, steps=10)
    page.mouse.up()

    spec = spec_of(page)
    into_plant = [c for c in spec["connections"] if c["to"] == ["plant", "u"]]
    assert len(into_plant) == 1
    assert into_plant[0]["from"] == ["pos", "y"]


# ----- saving -------------------------------------------------------------------


def test_saving_writes_the_edit_to_disk(page: Page, server: str):
    """The exit criterion for 7d: the file on disk changes."""
    open_diagram(page, server)
    drag(page, ".node[data-block='plant']", 80, -30)
    expect(page.get_by_test_id("dirty")).to_be_visible()

    expect(page.get_by_test_id("save-path")).to_have_value(DRAFT)
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")

    written = json.loads((REPO_ROOT / DRAFT).read_text())
    plant = next(b for b in written["blocks"] if b["name"] == "plant")
    assert plant["layout"] != {"x": 360.0, "y": 120.0}
    assert len(written["blocks"]) == 7  # everything else intact


def test_saving_clears_the_unsaved_marker(page: Page, server: str):
    open_diagram(page, server)
    drag(page, ".node[data-block='plant']", 30, 30)
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")
    expect(page.get_by_test_id("dirty")).to_be_hidden()


def test_saving_defaults_to_a_draft_rather_than_the_original(page: Page, server: str):
    """The committed diagram.json files are artefacts the tests assert against."""
    open_diagram(page, server)
    expect(page.get_by_test_id("save-path")).to_have_value(DRAFT)
    assert page.get_by_test_id("save-path").input_value() != EX2


def test_overwriting_an_existing_file_needs_confirmation(page: Page, server: str):
    open_diagram(page, server)
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")

    page.on("dialog", lambda d: d.dismiss())
    drag(page, ".node[data-block='plant']", 25, 25)
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_have_text("not saved")
    expect(page.get_by_test_id("dirty")).to_be_visible()


def test_confirming_the_overwrite_writes_it(page: Page, server: str):
    open_diagram(page, server)
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")
    first = (REPO_ROOT / DRAFT).read_text()

    page.on("dialog", lambda d: d.accept())
    drag(page, ".node[data-block='plant']", 90, 40)
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")
    assert (REPO_ROOT / DRAFT).read_text() != first


def test_work_in_progress_can_be_saved(page: Page, server: str):
    """An incomplete diagram is a normal editing state, not an error.

    A newly added block has an unconnected input, so the diagram will not *run* —
    but refusing to save half-finished work would make the editor hostile. The
    guard that matters is the next test: the file must load back.
    """
    open_diagram(page, server)
    page.get_by_test_id("add-block").select_option("Gain")
    expect(page.get_by_test_id("validity")).to_have_attribute("data-ok", "false")
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")
    written = json.loads((REPO_ROOT / DRAFT).read_text())
    assert "gain" in [b["name"] for b in written["blocks"]]


def test_a_spec_that_cannot_be_loaded_back_is_refused(page: Page, server: str):
    """Saving a document that will not reload turns a mistake into a broken file."""
    open_diagram(page, server)
    page.locator(".node[data-block='plant']").click()
    field = page.locator("[data-param='A']")
    field.fill("[[0,1,2],[3,4,5]]")  # not square
    field.blur()
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("not saved")
    assert not (REPO_ROOT / DRAFT).exists()


def test_a_saved_draft_reloads_and_reproduces_the_edit(page: Page, server: str):
    """Round trip: edit, save, reopen from disk, and the edit is there."""
    open_diagram(page, server)
    page.locator(".node[data-block='force']").click()
    page.locator("[data-param='omega']").fill("3.25")
    page.locator("[data-param='omega']").blur()
    page.get_by_test_id("save").click()
    expect(page.get_by_test_id("save-status")).to_contain_text("saved")

    page.reload()
    expect(page.get_by_test_id("status")).to_have_attribute("data-ready", "true")
    page.locator(f"[data-diagram-path='{DRAFT}']").click()
    expect(page.get_by_test_id("summary")).to_be_visible()
    force = next(b for b in spec_of(page)["blocks"] if b["name"] == "force")
    assert force["params"]["omega"] == 3.25
