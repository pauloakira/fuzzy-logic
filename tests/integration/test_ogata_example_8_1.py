"""Ogata Example 8-1, as a regression test with a published answer.

*Modern Control Engineering*, 5th ed., §8-2: a Ziegler-Nichols PID for
`G(s) = 1/(s(s+1)(s+5))`. Ogata derives the critical gain from Routh's criterion
and the oscillation frequency by substituting `s = jw`; this arrives at both
from a numerically broken loop and its gain margin, which is a completely
different route to the same numbers.
"""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.analysis import frequency_grid, frequency_response, margins, poles
from fuzzy.blocks import Gain, Select, StateSpacePlant, Step, Sum
from fuzzy.linearize import loop_transfer
from fuzzy.sim import Diagram, simulate
from fuzzy.spec import load

SPEC = "exercises/ogata_example_8_1/diagram.json"

# 1/(s(s+1)(s+5)) = 1/(s^3 + 6s^2 + 5s), controllable canonical form
A = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, -5.0, -6.0]])
B = np.array([[0.0], [0.0], [1.0]])


def proportional_loop() -> Diagram:
    """The same plant under unity feedback with `Kp = 1`, for the Z-N sweep."""
    d = Diagram("ogata_p")
    plant = StateSpacePlant(A, B, np.eye(3), np.zeros((3, 1)), x0=[0.0] * 3,
                            name="plant")
    total = Sum(("ref", "fb"), signs=(1.0, -1.0), name="total")
    d.connect(Step(final=1.0, t_step=0.0, name="ref"), (total, "ref"))
    d.connect(total, plant)
    d.connect(plant, Select(0, name="y"))
    d.connect(d.block("y"), Gain(1.0, name="ctrl"))
    d.connect(d.block("ctrl"), (total, "fb"))
    return d


def critical_point() -> tuple[float, float]:
    """`(Kcr, Pcr)` read off the loop transfer rather than from Routh's table."""
    lin = loop_transfer(proportional_loop(), at="total.y")
    w = frequency_grid(np.asarray(list(poles(lin.A)) + [1.0]), n=20000)
    h = frequency_response(lin.A, lin.B, lin.C, lin.D, w)[:, 0, 0]
    m = margins(w, h)
    return 10 ** (m["gain_margin_db"] / 20.0), 2 * np.pi / m["phase_crossover"]


def test_the_critical_gain_matches_ogatas_routh_result():
    """`s^3 + 6s^2 + 5s + Kp = 0` sustains oscillation at `Kp = 30`."""
    kcr, _ = critical_point()
    assert kcr == pytest.approx(30.0, rel=1e-3)


def test_the_oscillation_frequency_and_period_match():
    """Ogata substitutes `s = jw` and finds `w^2 = 5`."""
    _, pcr = critical_point()
    assert 2 * np.pi / pcr == pytest.approx(np.sqrt(5.0), rel=1e-3)
    assert pcr == pytest.approx(2.8099, rel=1e-3)


def test_the_ziegler_nichols_gains_match_the_book():
    kcr, pcr = critical_point()
    assert 0.6 * kcr == pytest.approx(18.0, rel=1e-3)          # Kp
    assert 0.5 * pcr == pytest.approx(1.405, rel=1e-3)          # Ti
    assert 0.125 * pcr == pytest.approx(0.35124, rel=1e-3)      # Td
    assert 0.6 * kcr * 0.125 * pcr == pytest.approx(6.3223, rel=1e-3)  # kd


def test_the_committed_diagram_carries_those_gains():
    pid = next(b for b in load(SPEC).blocks if b.name == "pid")
    assert pid.kp == pytest.approx(18.0)
    assert pid.ki == pytest.approx(18.0 / 1.405)
    assert pid.kd == pytest.approx(18.0 * 0.35124)
    # Ogata's ideal form; the practical default would not reproduce the book.
    assert pid.derivative_on == "error"


def test_the_step_response_overshoots_as_the_book_reports():
    """Ogata: "the maximum overshoot in the unit-step response is approximately
    62%"."""
    y = simulate(load(SPEC), t_max=16.0, dt_control=2e-4).col("plant.y", 0)
    assert 100 * (y.max() - 1.0) == pytest.approx(62.0, abs=1.5)
    assert y[-1] == pytest.approx(1.0, abs=0.01)   # integral action, no offset


def test_the_practical_pid_form_does_not_reproduce_the_book():
    """Same gains, derivative taken off the output instead of the error: same
    poles, different closed-loop zeros, 14 points more overshoot. Worth pinning,
    because the mismatch would otherwise read as a simulation bug."""
    spec = load(SPEC)
    pid = next(b for b in spec.blocks if b.name == "pid")
    pid.derivative_on = "output"
    y = simulate(spec, t_max=16.0, dt_control=2e-4).col("plant.y", 0)
    assert 100 * (y.max() - 1.0) == pytest.approx(75.6, abs=1.5)
