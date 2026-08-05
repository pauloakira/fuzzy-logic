"""API tests for the block editor — headless, no browser involved.

The point of building the backend first is that the interesting half of the
editor lands under the same test discipline as the library. These run in CI.
"""

from __future__ import annotations

import json
import sys

import pytest
from fastapi.testclient import TestClient

from editor.api import REPO_ROOT, app

EXERCISE = REPO_ROOT / "exercises" / "exercicio2_sdof_vibration_control"
sys.path.insert(0, str(EXERCISE))

client = TestClient(app)


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads((EXERCISE / "diagram.json").read_text())


# ----- palette ----------------------------------------------------------------


def test_palette_lists_every_registered_block():
    body = client.get("/api/palette").json()["blocks"]
    for expected in ("Harmonic", "Sum", "Select", "Saturation", "PIDBlock",
                     "StateSpacePlant", "FISBlock", "Observer", "sdof_plant"):
        assert expected in body


def test_palette_carries_enough_to_render_a_property_panel():
    harmonic = client.get("/api/palette").json()["blocks"]["Harmonic"]
    by_name = {p["name"]: p for p in harmonic["params"]}
    assert set(by_name) == {"amplitude", "omega", "phase"}
    assert by_name["omega"]["default"] == 1.0
    assert by_name["omega"]["required"] is False


def test_palette_carries_class_level_ports_for_drawing():
    blocks = client.get("/api/palette").json()["blocks"]
    assert blocks["Saturation"]["inputs"] == ["u"]
    assert blocks["Saturation"]["outputs"] == ["y"]
    assert blocks["Harmonic"]["inputs"] == []  # a source has none


def test_palette_is_json_safe_despite_infinite_defaults():
    """PIDBlock defaults lo/hi to +/-inf, which is not valid JSON."""
    raw = client.get("/api/palette").text
    assert "Infinity" not in raw and "NaN" not in raw
    params = client.get("/api/palette").json()["blocks"]["PIDBlock"]["params"]
    pid = {p["name"]: p for p in params}
    assert pid["lo"]["default"] is None  # non-finite defaults are nulled


# ----- discovery and loading --------------------------------------------------


def test_diagrams_lists_the_committed_specs():
    found = client.get("/api/diagrams").json()["diagrams"]
    assert "exercises/exercicio2_sdof_vibration_control/diagram.json" in found
    assert "exercises/exercicio1_motor_control/diagram.json" in found


def test_get_diagram_round_trips_through_the_library():
    path = "exercises/exercicio2_sdof_vibration_control/diagram.json"
    body = client.get("/api/diagram", params={"path": path}).json()
    committed = json.loads((REPO_ROOT / path).read_text())
    assert json.dumps(body["spec"], sort_keys=True) == json.dumps(
        committed, sort_keys=True
    )


def test_get_diagram_preserves_layout_for_the_canvas():
    path = "exercises/exercicio2_sdof_vibration_control/diagram.json"
    blocks = client.get("/api/diagram", params={"path": path}).json()["spec"]["blocks"]
    plant = next(b for b in blocks if b["name"] == "plant")
    assert plant["layout"] == {"x": 360.0, "y": 120.0}


def test_diagram_resolves_ports_per_block_instance():
    """Sum's ports come from its `ports` param and FISBlock's from the FIS, so
    neither can be read off the class — only the built diagram knows."""
    path = "exercises/exercicio2_sdof_vibration_control/diagram.json"
    ports = client.get("/api/diagram", params={"path": path}).json()["ports"]
    assert ports["total"]["inputs"] == ["ext", "ctrl"]
    assert ports["controller"]["inputs"] == ["deslocamento", "velocidade"]
    assert ports["controller"]["outputs"] == ["u"]
    assert ports["force"]["inputs"] == []


def test_validate_also_returns_ports():
    """After an edit the canvas needs ports again without reloading the file."""
    import json as _json

    spec = _json.loads(
        (EXERCISE / "diagram.json").read_text()
    )
    body = client.post("/api/validate", json={"spec": spec}).json()
    assert body["ports"]["controller"]["inputs"] == ["deslocamento", "velocidade"]


def test_path_traversal_is_refused():
    r = client.get("/api/diagram", params={"path": "../../../../etc/passwd"})
    assert r.status_code in (400, 404)
    assert "detail" in r.json()


def test_missing_file_is_404():
    r = client.get("/api/diagram", params={"path": "nope/diagram.json"})
    assert r.status_code == 404


def test_malformed_json_is_422(tmp_path, monkeypatch):
    bad = REPO_ROOT / "_api_test_bad.json"
    bad.write_text("{ not json")
    try:
        r = client.get("/api/diagram", params={"path": "_api_test_bad.json"})
        assert r.status_code == 422
        assert "invalid JSON" in r.json()["detail"]["error"]
    finally:
        bad.unlink()


# ----- validation -------------------------------------------------------------


def test_validate_accepts_the_committed_diagram(spec):
    body = client.post("/api/validate", json={"spec": spec}).json()
    assert body["ok"] is True
    assert body["problems"] == []
    assert body["n_states"] == 2
    assert set(body["blocks"]) >= {"plant", "controller", "actuator"}


def test_validate_reports_advice_the_canvas_should_show(spec):
    advice = client.post("/api/validate", json={"spec": spec}).json()["advice"]
    assert any("stability limit" in a for a in advice)
    assert any("slowest time constant" in a for a in advice)


def test_validate_returns_200_for_a_broken_diagram(spec):
    """A half-wired diagram is an expected canvas state, not a failed request."""
    broken = json.loads(json.dumps(spec))
    broken["connections"] = [
        c for c in broken["connections"] if c["to"] != ["plant", "u"]
    ]
    body = client.post("/api/validate", json={"spec": broken}).json()
    assert body["ok"] is False
    problem = body["problems"][0]
    assert problem["type"] == "WiringError"
    assert problem["block"] == "plant" and problem["port"] == "u"


def test_validate_surfaces_a_bad_membership_term_with_its_block(spec):
    broken = json.loads(json.dumps(spec))
    fis = next(b for b in broken["blocks"] if b["name"] == "controller")
    terms = fis["params"]["fis"]["inputs"]["deslocamento"]["terms"]
    terms["NG"]["params"] = [-0.3, -0.3]  # a shoulder with a == b -> NaN
    body = client.post("/api/validate", json={"spec": broken}).json()
    assert body["ok"] is False
    assert body["problems"][0]["block"] == "controller"
    assert "b > a" in body["problems"][0]["error"]


def test_validate_reports_an_algebraic_loop_with_every_block_in_it():
    spec = {
        "version": 1,
        "blocks": [
            {"type": "Gain", "name": "a", "params": {"k": 1.0}},
            {"type": "Gain", "name": "b", "params": {"k": 1.0}},
        ],
        "connections": [
            {"from": ["a", "y"], "to": ["b", "u"]},
            {"from": ["b", "y"], "to": ["a", "u"]},
        ],
    }
    body = client.post("/api/validate", json={"spec": spec}).json()
    assert body["ok"] is False
    assert body["problems"][0]["blocks"] == ["a", "b"]


# ----- simulation -------------------------------------------------------------


def test_simulate_reproduces_the_published_result(spec):
    body = client.post(
        "/api/simulate",
        json={"spec": spec, "t_max": 40.0, "dt_control": 0.005, "max_points": 20000},
    ).json()
    t = body["t"]
    x = body["signals"]["plant.y[0]"]
    window = [xi for ti, xi in zip(t, x, strict=True) if ti >= 36.0]
    assert max(abs(v) for v in window) == pytest.approx(0.0734, abs=5e-4)


def test_simulate_splits_vector_signals_per_component(spec):
    body = client.post("/api/simulate", json={"spec": spec, "t_max": 1.0}).json()
    assert "plant.y[0]" in body["signals"] and "plant.y[1]" in body["signals"]
    assert "plant.y" not in body["signals"]


def test_simulate_decimates_large_runs(spec):
    body = client.post(
        "/api/simulate", json={"spec": spec, "t_max": 40.0, "max_points": 500}
    ).json()
    assert body["n_samples"] == 8001
    assert body["returned"] <= 500
    assert len(body["t"]) == len(body["signals"]["plant.y[0]"])


def test_simulate_returns_warnings_rather_than_swallowing_them(spec):
    """The RK4 stability guard is usually the most useful thing on the screen."""
    body = client.post(
        "/api/simulate", json={"spec": spec, "t_max": 5.0, "dt_control": 0.35}
    ).json()
    assert any("stability limit" in w for w in body["warnings"])


def test_simulate_refuses_an_unbounded_horizon(spec):
    r = client.post("/api/simulate", json={"spec": spec, "t_max": 1e9})
    assert r.status_code == 422  # pydantic bound, before any work is done


def test_simulate_rejects_a_broken_spec_with_structured_detail(spec):
    broken = json.loads(json.dumps(spec))
    broken["blocks"] = [b for b in broken["blocks"] if b["name"] != "actuator"]
    r = client.post("/api/simulate", json={"spec": broken, "t_max": 1.0})
    assert r.status_code == 422
    assert "block" in r.json()["detail"] or "error" in r.json()["detail"]


def test_simulate_accepts_a_hand_written_minimal_spec():
    """A spec authored by hand, never through the library, must work."""
    spec = {
        "version": 1,
        "name": "hand written",
        "blocks": [
            {"type": "Harmonic", "name": "src",
             "params": {"amplitude": 2.0, "omega": 1.0, "phase": 0.0}},
            {"type": "Saturation", "name": "sat", "params": {"lo": -1.0, "hi": 1.0}},
        ],
        "connections": [{"from": ["src", "y"], "to": ["sat", "u"]}],
    }
    body = client.post("/api/simulate", json={"spec": spec, "t_max": 10.0}).json()
    assert max(body["signals"]["sat.y"]) == pytest.approx(1.0)
    assert min(body["signals"]["sat.y"]) == pytest.approx(-1.0)


# ----- analyze (Bode, poles/zeros) --------------------------------------------


def test_analyze_returns_bode_and_poles_for_the_sdof_plant(spec):
    body = client.post("/api/analyze", json={"spec": spec}).json()
    systems = body["systems"]
    plant = next(s for s in systems if s["name"] == "plant")
    assert len(plant["poles"]) == 2                       # a 2-state SDOF plant
    n = len(plant["omega"])
    assert n >= 32
    for ch in plant["channels"]:
        assert len(ch["mag_db"]) == n
        assert len(ch["phase_deg"]) == n
    # The velocity channel of an SDOF plant has one transfer zero at the origin.
    vel = next(ch for ch in plant["channels"] if ch["label"] == "plant.y[1]")
    assert len(vel["zeros"]) == 1
    assert abs(vel["zeros"][0][0]) < 1e-6 and abs(vel["zeros"][0][1]) < 1e-6


def test_analyze_is_empty_without_an_lti_plant():
    """A diagram with no StateSpacePlant has nothing to analyse, and says so."""
    spec = {
        "version": 1,
        "name": "no plant",
        "blocks": [
            {"type": "Harmonic", "name": "src",
             "params": {"amplitude": 1.0, "omega": 1.0, "phase": 0.0}},
            {"type": "Saturation", "name": "sat", "params": {"lo": -1.0, "hi": 1.0}},
        ],
        "connections": [{"from": ["src", "y"], "to": ["sat", "u"]}],
    }
    body = client.post("/api/analyze", json={"spec": spec}).json()
    assert body["systems"] == []


def test_analyze_linearizes_a_nonlinear_plant():
    """`MotorPlant` has no (A,B,C,D); it gets one from a Jacobian, and says so."""
    spec = json.loads(
        (REPO_ROOT / "exercises/exercicio1_motor_control/diagram.json").read_text()
    )
    body = client.post("/api/analyze", json={"spec": spec}).json()
    plant = next(s for s in body["systems"] if s["name"] == "plant")
    assert plant["linearized"] is True
    assert len(plant["poles"]) == 2
    assert len(plant["channels"]) == 2


def test_analyze_reports_that_the_default_operating_point_is_on_a_limit():
    """The motor starts at (0 rpm, 0 V), which is both lower clamps at once — the
    linearization there is a model of a corner, and must not pass silently."""
    spec = json.loads(
        (REPO_ROOT / "exercises/exercicio1_motor_control/diagram.json").read_text()
    )
    body = client.post("/api/analyze", json={"spec": spec}).json()
    plant = next(s for s in body["systems"] if s["name"] == "plant")
    assert any("not differentiable" in w for w in plant["warnings"])


def test_analyze_takes_an_operating_point_and_the_warnings_go_away():
    """Moved off the clamps the motor is smooth, and the model is trustworthy."""
    spec = json.loads(
        (REPO_ROOT / "exercises/exercicio1_motor_control/diagram.json").read_text()
    )
    body = client.post(
        "/api/analyze",
        json={
            "spec": spec,
            "operating_point": {"plant": {"x": [500.0, 50.0], "u": {"u": 0.0}}},
        },
    ).json()
    plant = next(s for s in body["systems"] if s["name"] == "plant")
    assert plant["warnings"] == []
    # omega' = k V - omega with k = 10 gives one mode at -1 plus the V integrator
    reals = sorted(round(p[0], 6) for p in plant["poles"])
    assert reals == [-1.0, 0.0]


def test_analyze_marks_a_genuine_lti_plant_as_not_linearized(spec):
    body = client.post("/api/analyze", json={"spec": spec}).json()
    plant = next(s for s in body["systems"] if s["name"] == "plant")
    assert plant["linearized"] is False
    assert plant["warnings"] == []


def test_analyze_returns_the_loop_transfer_with_its_margins(spec):
    body = client.post("/api/analyze", json={"spec": spec}).json()
    loop = next(s for s in body["systems"] if s["kind"] == "loop")
    assert loop["loop_break"] == "total.y"
    assert loop["margins"]["phase_margin_deg"] > 0
    # this loop's phase approaches -180 without reaching it
    assert loop["margins"]["gain_margin_db"] is None
    assert len(loop["nyquist"]) == len(loop["omega"])


def test_the_root_locus_passes_through_the_actual_closed_loop(spec):
    """A locus that misses the design point is drawing a different system."""
    body = client.post("/api/analyze", json={"spec": spec}).json()
    loop = next(s for s in body["systems"] if s["kind"] == "loop")
    closed = next(s for s in body["systems"] if s["kind"] == "diagram")

    gains = loop["locus"]["gains"]
    at_one = gains.index(min(gains, key=lambda g: abs(g - 1.0)))
    drawn = sorted(
        (b[at_one][0], b[at_one][1]) for b in loop["locus"]["branches"]
    )
    want = sorted((p[0], p[1]) for p in closed["poles"])
    for (a, b), (c, d) in zip(drawn, want, strict=True):
        assert a == pytest.approx(c, abs=1e-6) and b == pytest.approx(d, abs=1e-6)


def test_the_root_locus_starts_at_the_open_loop_poles(spec):
    body = client.post("/api/analyze", json={"spec": spec}).json()
    loop = next(s for s in body["systems"] if s["kind"] == "loop")
    plant = next(s for s in body["systems"] if s["kind"] == "block")
    at_zero = loop["locus"]["gains"].index(0.0)
    drawn = sorted((b[at_zero][0], b[at_zero][1]) for b in loop["locus"]["branches"])
    want = sorted((p[0], p[1]) for p in plant["poles"])
    for (a, b), (c, d) in zip(drawn, want, strict=True):
        assert a == pytest.approx(c, abs=1e-6) and b == pytest.approx(d, abs=1e-6)
