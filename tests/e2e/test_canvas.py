"""Browser tests for the SVG canvas (step 7c).

Exit criterion for 7c, from the design note: exercise 2's `diagram.json` draws
with correct node positions and wires. These assert exactly that, plus the
things a canvas gets silently wrong — ports resolved per block instance, sources
and sampled blocks drawn differently, and diagrams with no layout at all.
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


# ----- structure ---------------------------------------------------------------


def test_canvas_draws_every_block_and_wire(page: Page, server: str):
    open_diagram(page, server)
    canvas = page.get_by_test_id("canvas")
    expect(canvas).to_have_attribute("data-nodes", "7")
    expect(canvas).to_have_attribute("data-wires", "8")
    expect(page.get_by_test_id("nodes").locator(".node")).to_have_count(7)
    expect(page.get_by_test_id("wires").locator(".wire")).to_have_count(8)


def test_nodes_sit_at_their_spec_coordinates(page: Page, server: str):
    """The whole point of `layout` surviving the round trip."""
    open_diagram(page, server)
    plant = page.locator(".node[data-block='plant']")
    expect(plant).to_have_attribute("data-x", "360")
    expect(plant).to_have_attribute("data-y", "120")
    force = page.locator(".node[data-block='force']")
    expect(force).to_have_attribute("data-x", "40")
    expect(force).to_have_attribute("data-y", "40")


def test_nodes_are_labelled_with_name_and_type(page: Page, server: str):
    open_diagram(page, server)
    plant = page.locator(".node[data-block='plant']")
    expect(plant.locator(".node-name")).to_have_text("plant")
    expect(plant.locator(".node-type")).to_have_text("StateSpacePlant")


def test_wires_name_both_endpoints(page: Page, server: str):
    open_diagram(page, server)
    expect(
        page.locator("[data-wire='force.y->total.ext']")
    ).to_have_count(1)
    # the feedback wire that closes the loop
    expect(page.locator("[data-wire='actuator.y->total.ctrl']")).to_have_count(1)


def test_shapes_distinguish_sources_and_sampled_blocks(page: Page, server: str):
    """Matches `to_mermaid()`, so the live view and the report figure agree."""
    open_diagram(page, server)
    # a source has no inputs -> parallelogram
    expect(page.locator(".node[data-block='force'] polygon")).to_have_count(1)
    # a continuous block -> square-cornered rect
    plant_rx = page.locator(".node[data-block='plant'] rect").get_attribute("rx")
    assert float(plant_rx) < 10
    # a sampled block -> fully rounded
    ctrl_rx = page.locator(".node[data-block='controller'] rect").get_attribute("rx")
    assert float(ctrl_rx) > 20


def test_ports_are_drawn_from_instance_resolved_names(page: Page, server: str):
    """FISBlock's inputs come from its FIS; no class introspection could know."""
    open_diagram(page, server)
    expect(page.locator("[data-port='controller.deslocamento']")).to_have_count(1)
    expect(page.locator("[data-port='controller.velocidade']")).to_have_count(1)
    # Sum's ports come from its `ports` parameter
    expect(page.locator("[data-port='total.ext']")).to_have_count(1)
    expect(page.locator("[data-port='total.ctrl']")).to_have_count(1)


# ----- wire routing --------------------------------------------------------------


def segments(page: Page, wire: str) -> list[tuple[float, float]]:
    """The `d` of a wire as a list of points."""
    d = page.locator(f"[data-wire='{wire}']").get_attribute("d")
    pts = []
    for chunk in d.replace("M", " ").replace("L", " ").split():
        pts.append(float(chunk))
    return list(zip(pts[0::2], pts[1::2], strict=True))


def test_every_wire_segment_is_horizontal_or_vertical(page: Page, server: str):
    """Orthogonal routing, as every block-diagram tool draws it.

    Diagonal splines were unreadable once more than a couple of wires crossed.
    """
    open_diagram(page, server)
    wires = page.eval_on_selector_all(
        "[data-wire]", "els => els.map(e => e.dataset.wire)"
    )
    assert len(wires) == 8
    for wire in wires:
        pts = segments(page, wire)
        assert len(pts) >= 2, wire
        for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
            axis_aligned = abs(x1 - x2) < 0.02 or abs(y1 - y2) < 0.02
            assert axis_aligned, f"{wire} has a diagonal segment"


def test_wires_have_no_curves(page: Page, server: str):
    """No bezier or arc commands at all — corners are sharp."""
    open_diagram(page, server)
    ds = page.eval_on_selector_all(
        "[data-wire]", "els => els.map(e => e.getAttribute('d'))"
    )
    for d in ds:
        assert not any(c in d for c in "CcSsQqTtAa"), d


def test_a_wire_between_aligned_ports_is_a_single_straight_run(page: Page, server: str):
    open_diagram(page, server)
    pts = segments(page, "total.y->plant.u")
    assert len(pts) == 2
    assert abs(pts[0][1] - pts[1][1]) < 0.02


def test_a_feedback_wire_routes_below_rather_than_across(page: Page, server: str):
    """`actuator` sits right of `total`, so the wire must go around."""
    open_diagram(page, server)
    pts = segments(page, "actuator.y->total.ctrl")
    assert len(pts) > 2
    lowest = max(y for _, y in pts)
    actuator_bottom = 260 + 52  # layout y + node height
    assert lowest > actuator_bottom, "feedback should drop below the blocks it joins"


def test_wires_carry_an_arrowhead(page: Page, server: str):
    """Direction should be readable without tracing the line."""
    open_diagram(page, server)
    wire = page.locator("[data-wire='force.y->total.ext']")
    assert wire.get_attribute("marker-end") == "url(#wire-arrow)"
    assert page.locator("#wire-arrow").count() == 1


def test_viewbox_fits_the_drawn_content(page: Page, server: str):
    open_diagram(page, server)
    box = page.get_by_test_id("canvas").get_attribute("viewBox")
    min_x, min_y, width, height = (float(v) for v in box.split())
    assert min_x <= 40 and min_y <= 40  # includes the leftmost/topmost node
    assert width > 700 and height > 200  # spans the whole diagram
    assert width > height  # a block diagram is wide and flat


# ----- selection ---------------------------------------------------------------


def test_clicking_a_node_selects_it_and_shows_its_parameters(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='plant']").click()

    expect(page.locator(".node[data-block='plant']")).to_have_attribute(
        "data-selected", "true"
    )
    expect(page.get_by_test_id("selection")).to_be_visible()
    expect(page.get_by_test_id("selected-name")).to_have_text("plant")
    expect(page.get_by_test_id("selected-type")).to_have_text("StateSpacePlant")
    expect(page.get_by_test_id("selected-params")).to_contain_text("A")


def test_only_one_node_is_selected_at_a_time(page: Page, server: str):
    open_diagram(page, server)
    page.locator(".node[data-block='plant']").click()
    page.locator(".node[data-block='controller']").click()
    expect(page.locator(".node[data-selected]")).to_have_count(1)
    expect(page.get_by_test_id("selected-name")).to_have_text("controller")


def test_a_node_can_be_selected_from_the_keyboard(page: Page, server: str):
    """Nodes are focusable and Enter activates them, so the canvas is not
    mouse-only."""
    open_diagram(page, server)
    node = page.locator(".node[data-block='plant']")
    node.focus()
    node.press("Enter")
    expect(node).to_have_attribute("data-selected", "true")


def test_selecting_a_fis_block_exposes_it_as_editable_json(page: Page, server: str):
    """The controller's `fis` is a 25-rule document.

    It gets a JSON textarea rather than a one-line field — honest about what it
    is, and editable, which is what step 7f will build on.
    """
    import json

    open_diagram(page, server)
    page.locator(".node[data-block='controller']").click()
    params = page.get_by_test_id("selected-params")
    expect(params).to_contain_text("fis")  # the parameter is listed
    field = page.locator("textarea[data-param='fis']")
    expect(field).to_have_count(1)
    document = json.loads(field.input_value())
    assert len(document["rules"]) == 25
    assert set(document["inputs"]) == {"deslocamento", "velocidade"}


# ----- other diagrams ----------------------------------------------------------


def test_exercise_one_also_draws(page: Page, server: str):
    open_diagram(page, server, EX1)
    canvas = page.get_by_test_id("canvas")
    expect(canvas).to_have_attribute("data-nodes", "5")
    expect(canvas).to_have_attribute("data-wires", "6")
    expect(page.locator(".node[data-block='plant'] .node-type")).to_have_text(
        "MotorPlant"
    )


def test_switching_diagrams_replaces_the_drawing(page: Page, server: str):
    open_diagram(page, server, EX2)
    expect(page.get_by_test_id("nodes").locator(".node")).to_have_count(7)
    page.locator(f"[data-diagram-path='{EX1}']").click()
    expect(page.get_by_test_id("nodes").locator(".node")).to_have_count(5)


def test_a_diagram_without_layout_still_draws(page: Page, server: str):
    """A spec authored by hand carries no positions; it must not collapse."""
    open_diagram(page, server)
    placed = page.evaluate(
        """() => {
          const spec = structuredClone(window.__lastSpec);
          for (const b of spec.blocks) delete b.layout;
          return spec;
        }"""
    )
    result = page.evaluate(
        """async (spec) => {
          const { renderDiagram } = await import('/static/canvas.js');
          const svg = document.getElementById('canvas');
          const r = await fetch('/api/validate', {
            method: 'POST',
            headers: {'content-type': 'application/json'},
            body: JSON.stringify({spec}),
          }).then((x) => x.json());
          return renderDiagram(svg, spec, r.ports);
        }""",
        placed,
    )
    assert result["nodes"] == 7 and result["wires"] == 8
    assert result["unplaced"] == 7
    expect(page.locator(".node[data-auto-placed]")).to_have_count(7)

    # auto-placed nodes must not all land on top of each other
    xs = page.eval_on_selector_all(
        ".node", "els => els.map(e => Number(e.dataset.x))"
    )
    assert len(set(xs)) > 1
