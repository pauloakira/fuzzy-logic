"""Integration tests: the published exercise-2 results must not silently move.

The unit tests cover the library in pieces. This pins the numbers that actually
appear in `REPORT.md` and `REPORT_comparison.md`, so a refactor that quietly
changes a documented result fails here rather than in a reader's eye.

Tolerances are loose enough for cross-platform float variation and tight enough
that any real behavioural change trips them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

EXERCISE = (
    Path(__file__).resolve().parents[2]
    / "exercises"
    / "exercicio2_sdof_vibration_control"
)
sys.path.insert(0, str(EXERCISE))

import sdof_vibration as S  # noqa: E402
from pid_comparison import PID_PORTS, pid_controller  # noqa: E402

from fuzzy.metrics import steady_state  # noqa: E402
from fuzzy.sim import simulate  # noqa: E402
from fuzzy.spec import load  # noqa: E402


def metrics(controller=None, ports=S.FUZZY_PORTS):
    log = simulate(
        S.build_diagram(controller, ports=ports, name="t"),
        t_max=S.T_MAX,
        dt_control=S.DT,
    )
    out = steady_state(log, "plant.y", window=S.METRIC_WINDOW, index=0, tau=S.TAU)
    if "actuator.y" in log.signals:
        out["u_peak"] = steady_state(
            log, "actuator.y", window=S.METRIC_WINDOW
        )["peak"]
    return out


# ----- published numbers ------------------------------------------------------


def test_open_loop_matches_the_analytic_resonant_amplitude():
    """The horizon must be long enough to reach F0/(c*omega_n) = 0.25 m."""
    m = metrics(None)
    assert m["peak"] == pytest.approx(S.F0 / (S.C * S.OMEGA_N), rel=2e-3)
    assert m["peak"] == pytest.approx(0.2499, abs=5e-4)
    assert m["rms"] == pytest.approx(0.1782, abs=5e-4)


def test_fuzzy_controller_matches_the_report():
    m = metrics(S.fuzzy_controller())
    assert m["peak"] == pytest.approx(0.0734, abs=5e-4)
    assert m["rms"] == pytest.approx(0.0521, abs=5e-4)
    assert m["u_peak"] == pytest.approx(0.737, abs=2e-3)


def test_pid_controller_matches_the_report():
    m = metrics(pid_controller(), ports=PID_PORTS)
    assert m["peak"] == pytest.approx(0.0093, abs=5e-4)
    assert m["rms"] == pytest.approx(0.0066, abs=5e-4)
    assert m["u_peak"] == pytest.approx(0.965, abs=5e-3)


def test_reduction_percentages_quoted_in_the_reports():
    open_m = metrics(None)
    fuzzy = metrics(S.fuzzy_controller())
    pid = metrics(pid_controller(), ports=PID_PORTS)
    assert 100 * (1 - fuzzy["peak"] / open_m["peak"]) == pytest.approx(70.6, abs=0.3)
    assert 100 * (1 - pid["peak"] / open_m["peak"]) == pytest.approx(96.3, abs=0.3)


def test_scaling_gain_10_closes_the_gap_to_pid():
    """The comparison report's central claim, pinned."""
    fuzzy = metrics(S.fuzzy_controller(gain=10.0))
    pid = metrics(pid_controller(), ports=PID_PORTS)
    assert fuzzy["peak"] == pytest.approx(0.0102, abs=5e-4)
    assert fuzzy["peak"] < 1.15 * pid["peak"], "fuzzy should be within ~15% of PID"
    assert fuzzy["u_peak"] == pytest.approx(pid["u_peak"], rel=0.05), (
        "at comparable effort"
    )


# ----- controller integrity ---------------------------------------------------


def test_controller_validates_clean():
    assert S.build_fis_spec().validate() == []


def test_rule_base_is_complete_and_partitions_are_strong():
    spec = S.build_fis_spec()
    assert len(S.RULES) == 25
    assert S.RULES.coverage(spec.term_names()) == 1.0
    for var in (S.DISP, S.VEL, S.FORCE):
        assert var.partition_error() == pytest.approx(0.0, abs=1e-12)


def test_centroid_cannot_reach_the_declared_actuator_limit():
    """Documented in REPORT.md §11: the reachable range is +/-2.505 N of +/-3 N."""
    fis = S.build_fis()
    grid = [
        fis.evaluate({"deslocamento": float(x), "velocidade": float(v)})
        for x in np.linspace(-S.X_MAX, S.X_MAX, 31)
        for v in np.linspace(-S.V_MAX, S.V_MAX, 31)
    ]
    assert max(grid) == pytest.approx(2.505, abs=1e-3)
    assert max(grid) < S.U_MAX


# ----- the committed spec file ------------------------------------------------


def test_committed_diagram_json_is_self_contained():
    """The editor fixture must load with nothing supplied at runtime."""
    path = EXERCISE / "diagram.json"
    assert "$provide" not in path.read_text()
    d = load(path)  # no objects=
    assert len(d.blocks) == 7
    assert len(d.connections()) == 8


def test_committed_diagram_json_reproduces_the_in_memory_diagram():
    a = simulate(
        S.build_diagram(S.fuzzy_controller(), name="mem"), t_max=5.0, dt_control=S.DT
    )
    b = simulate(load(EXERCISE / "diagram.json"), t_max=5.0, dt_control=S.DT)
    assert np.array_equal(a.col("plant.y", 0), b.col("plant.y", 0))


def test_mermaid_figure_matches_the_executable_diagram():
    """The published block diagram is generated, so it must not have drifted."""
    committed = (EXERCISE / "diagram.mmd").read_text().strip()
    fresh = S.build_diagram(
        S.fuzzy_controller(), name="ex2_sdof_fuzzy"
    ).to_mermaid().strip()
    assert committed == fresh


def test_report_embeds_the_current_mermaid_diagram():
    """REPORT.md §8.1 must hold exactly what diagram.mmd holds."""
    mmd = (EXERCISE / "diagram.mmd").read_text().strip()
    report = (EXERCISE / "REPORT.md").read_text()
    assert f"```mermaid\n{mmd}\n```" in report


def test_committed_diagram_json_is_in_sync_with_the_script():
    """Regenerating the spec must not change it — the file cannot drift."""
    from fuzzy.spec import to_spec

    committed = json.loads((EXERCISE / "diagram.json").read_text())
    fresh = to_spec(
        S.build_diagram(S.fuzzy_controller(), name="ex2_sdof_fuzzy")
    )
    assert json.dumps(fresh, sort_keys=True) == json.dumps(committed, sort_keys=True)
