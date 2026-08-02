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
