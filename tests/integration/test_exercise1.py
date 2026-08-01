"""Integration tests pinning the published exercise-1 results.

Exercise 1's report previously contained two errors that a test would have
caught: the FIS output was labelled rpm/s while being applied as V/s, and §6
claimed an equilibrium along the whole `omega = 10V` diagonal when only a single
point qualifies. Both corrected claims are asserted here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

EXERCISE = (
    Path(__file__).resolve().parents[2] / "exercises" / "exercicio1_motor_control"
)
sys.path.insert(0, str(EXERCISE))

import motor_control as MC  # noqa: E402


def test_pointwise_table_matches_the_report():
    """§7's table. Static FIS evaluation, so the port cannot have moved it."""
    fis = MC.build_fis()
    expected = {
        (0, 0): 0.6683,
        (200, 20): 0.1771,
        (500, 50): 0.0000,
        (700, 70): -0.0764,
        (900, 90): -0.3470,
        (1000, 100): -0.6683,
    }
    for (om, v), want in expected.items():
        got = fis.evaluate({"velocidade": float(om), "alimentacao": float(v)})
        assert got == pytest.approx(want, abs=5e-4), (om, v)


def test_only_one_point_on_the_diagonal_is_an_equilibrium():
    """The corrected §6 claim: (500, 50) is the sole fixed point, not the line."""
    fis = MC.build_fis()
    on_diagonal = {
        om: fis.evaluate({"velocidade": float(om), "alimentacao": om / 10.0})
        for om in (0, 200, 500, 800, 1000)
    }
    assert on_diagonal[500] == pytest.approx(0.0, abs=1e-9)
    for om, u in on_diagonal.items():
        if om != 500:
            assert abs(u) > 1e-3, f"omega={om} should not be an equilibrium"


def test_output_is_a_voltage_rate_not_a_speed_rate():
    """The corrected §2 claim: the two rates differ by the plant gain of 10.

    A commanded +1 V/s asks for `K = 10` rpm/s of equilibrium-speed change, which
    the plant's own limiter clips to 1 rpm/s. The gap is not academic — voltage
    runs far ahead of the speed it commands during the transient.
    """
    log = MC.run(x0=0.0, v0=0.0, t_max=800.0)
    omega, V = log.col("plant.y", 0), log.col("plant.y", 1)
    lead = V - omega / MC.K
    assert np.max(np.abs(lead)) == pytest.approx(48.1, abs=0.5)
    assert MC.K == 10.0


def test_convergence_is_slow_and_the_report_says_so():
    """The corrected §9/§10 claim: t=800 s is ~15% away, not 'converged'."""
    rest = MC.run(x0=0.0, v0=0.0, t_max=800.0)
    sat = MC.run(x0=1000.0, v0=100.0, t_max=800.0)
    assert rest.col("plant.y", 0)[-1] == pytest.approx(577.2, abs=1.0)
    assert sat.col("plant.y", 0)[-1] == pytest.approx(422.8, abs=1.0)
    # both still well away from the (500, 50) fixed point
    assert abs(rest.col("plant.y", 0)[-1] - 500.0) > 50.0
    assert abs(sat.col("plant.y", 0)[-1] - 500.0) > 50.0


def test_controller_validates_and_covers_its_rule_base():
    spec = MC.build_fis_spec()
    assert spec.validate() == []
    assert spec.rules.coverage(spec.term_names()) == 1.0


def test_diagram_json_is_self_contained():
    from fuzzy.spec import load

    path = EXERCISE / "diagram.json"
    assert "$provide" not in path.read_text()
    load(path)  # no objects= needed


def test_motor_plant_states_stay_inside_their_physical_bounds():
    """The clamps are enforced on the derivative; check they actually hold."""
    log = MC.run(x0=0.0, v0=0.0, t_max=800.0)
    omega, V = log.col("plant.y", 0), log.col("plant.y", 1)
    assert omega.min() >= -1e-9 and omega.max() <= MC.OMEGA_MAX + 1e-9
    assert V.min() >= -1e-9 and V.max() <= MC.V_MAX + 1e-9
