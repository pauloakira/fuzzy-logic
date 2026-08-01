"""Unit tests for LQR and observer design, and the Observer block."""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.blocks import (
    Constant,
    Gain,
    Harmonic,
    Observer,
    StateFeedback,
    Sum,
    sdof_plant,
)
from fuzzy.lti import RiccatiError, are_residual, lqr, observer_gain, solve_care
from fuzzy.sim import Diagram, simulate

M, C, K = 1.0, 0.4, 100.0
A_SDOF = np.array([[0.0, 1.0], [-K / M, -C / M]])
B_SDOF = np.array([[0.0], [1.0 / M]])
C_POS = np.array([[1.0, 0.0]])  # displacement is all a real sensor gives


# ----- Riccati -----------------------------------------------------------------


def test_double_integrator_position_cost_matches_closed_form():
    """Q = diag(1, 0), R = 1 on a double integrator gives K = [1, sqrt(2)]."""
    A, B = [[0.0, 1.0], [0.0, 0.0]], [[0.0], [1.0]]
    Kg, _, ev = lqr(A, B, np.diag([1.0, 0.0]), [[1.0]])
    assert Kg.ravel() == pytest.approx([1.0, np.sqrt(2.0)])
    assert np.all(np.real(ev) < 0)


def test_double_integrator_identity_cost_matches_closed_form():
    """Q = I is a *different* problem: the algebra gives K = [1, sqrt(3)].

    Recorded because [1, sqrt(2)] is the more commonly quoted figure and applies
    only when velocity is not penalised.
    """
    A, B = [[0.0, 1.0], [0.0, 0.0]], [[0.0], [1.0]]
    Kg, _, _ = lqr(A, B, np.eye(2), [[1.0]])
    assert Kg.ravel() == pytest.approx([1.0, np.sqrt(3.0)])


@pytest.mark.parametrize("q11", [1.0, 1e2, 1e4, 1e6])
def test_care_residual_is_negligible(q11):
    Q, R = np.diag([q11, 1.0]), np.array([[1.0]])
    P = solve_care(A_SDOF, B_SDOF, Q, R)
    scale = max(1.0, float(np.max(np.abs(P))))
    assert are_residual(A_SDOF, B_SDOF, Q, R, P) / scale < 1e-9


def test_care_solution_is_symmetric_and_positive_definite():
    P = solve_care(A_SDOF, B_SDOF, np.diag([1e4, 1.0]), [[1.0]])
    assert np.allclose(P, P.T)
    assert np.all(np.linalg.eigvalsh(P) > 0)


def test_lqr_closed_loop_is_always_stable():
    for q11 in (1.0, 1e3, 1e6):
        _, _, ev = lqr(A_SDOF, B_SDOF, np.diag([q11, 1.0]), [[1.0]])
        assert np.all(np.real(ev) < 0)


def test_heavier_state_cost_gives_faster_poles():
    _, _, slow = lqr(A_SDOF, B_SDOF, np.diag([1e2, 1.0]), [[1.0]])
    _, _, fast = lqr(A_SDOF, B_SDOF, np.diag([1e6, 1.0]), [[1.0]])
    assert abs(np.real(fast[0])) > abs(np.real(slow[0]))


def test_uncontrollable_pair_raises():
    with pytest.raises(RiccatiError):
        lqr([[1.0, 0.0], [0.0, 1.0]], [[1.0], [0.0]], np.eye(2), [[1.0]])


def test_singular_R_raises():
    with pytest.raises(RiccatiError, match="invertible"):
        lqr(A_SDOF, B_SDOF, np.eye(2), [[0.0]])


def test_mismatched_shapes_raise():
    with pytest.raises(RiccatiError, match="as many rows"):
        lqr(A_SDOF, [[1.0], [1.0], [1.0]], np.eye(2), [[1.0]])


# ----- Observer design ---------------------------------------------------------


def test_observer_poles_are_stable_and_faster_than_the_plant():
    L, ev = observer_gain(A_SDOF, C_POS, np.eye(2), [[1e-4]])
    assert np.all(np.real(ev) < 0)
    plant_rate = abs(np.real(np.linalg.eigvals(A_SDOF)[0]))
    assert abs(np.real(ev)).min() > plant_rate


def test_trusting_the_sensor_less_gives_a_smaller_gain():
    tight, _ = observer_gain(A_SDOF, C_POS, np.eye(2), [[1e-4]])
    loose, _ = observer_gain(A_SDOF, C_POS, np.eye(2), [[1e-1]])
    assert np.linalg.norm(loose) < np.linalg.norm(tight)


# ----- Observer block ----------------------------------------------------------


def observed_loop(x0_err: float, rn: float = 1e-4):
    """Plant driven open loop, with an observer started from the wrong state."""
    L, _ = observer_gain(A_SDOF, C_POS, np.eye(2), [[rn]])
    d = Diagram()
    plant = sdof_plant(M, C, K, x0=0.1, name="plant")
    # The sensor is explicit: the observer must see only C @ x, never the full
    # state, or the exercise assumes away the thing it is meant to demonstrate.
    sensor = Gain(C_POS, name="sensor")
    obs = Observer(A_SDOF, B_SDOF, C_POS, L, x0=[0.1 + x0_err, 0.0], name="obs")
    d.connect(Constant(0.0, name="zero"), plant)
    d.connect(plant, sensor)
    d.connect(sensor, (obs, "y"))
    d.connect(Constant(0.0, name="u0"), (obs, "u"))
    return d, plant


def test_observer_estimate_converges_to_the_true_state():
    """The whole point: a wrong initial estimate must decay to the truth.

    Run to 10 s, not 5: the designed observer poles are -99 and -1.48, so the
    slow mode needs ~7 s to fall five orders of magnitude. The horizon follows
    the design, rather than the threshold being loosened to fit a short run.
    """
    d, _ = observed_loop(x0_err=0.5)
    log = simulate(d, t_max=10.0, dt_control=0.002)
    err_x = log.col("plant.y", 0) - log.col("obs.xhat", 0)
    err_v = log.col("plant.y", 1) - log.col("obs.xhat", 1)
    assert err_x[0] == pytest.approx(-0.5, abs=1e-9)  # starts 0.5 m wrong
    assert abs(err_x[-1]) < 1e-6
    assert abs(err_v[-1]) < 1e-4


def test_observer_estimates_the_unmeasured_velocity():
    """It sees displacement only, yet reconstructs velocity."""
    d, _ = observed_loop(x0_err=0.0)
    log = simulate(d, t_max=5.0, dt_control=0.002)
    late = log.t >= 2.0
    true_v = log.col("plant.y", 1)[late]
    est_v = log.col("obs.xhat", 1)[late]
    assert np.max(np.abs(true_v - est_v)) < 1e-5


def test_observer_contributes_its_own_states_to_the_diagram():
    d, _ = observed_loop(x0_err=0.1)
    assert d.n_states == 4  # 2 plant + 2 observer (the sensor is algebraic)


def test_observer_output_feedback_stabilises_the_plant():
    """LQR gains on estimated state, sensing displacement only."""
    Kg, _, _ = lqr(A_SDOF, B_SDOF, np.diag([1e4, 1.0]), [[1.0]])
    L, _ = observer_gain(A_SDOF, C_POS, np.eye(2), [[1e-4]])

    d = Diagram()
    plant = sdof_plant(M, C, K, name="plant")
    obs = Observer(A_SDOF, B_SDOF, C_POS, L, name="obs")
    ctrl = StateFeedback(Kg.ravel(), name="k")
    force = Harmonic(amplitude=1.0, omega=np.sqrt(K / M), name="force")
    total = Sum(("ext", "ctrl"), name="total")
    d.connect(force, (total, "ext"))
    d.connect(ctrl, (total, "ctrl"))
    d.connect(total, plant)
    d.connect(plant, Gain(C_POS, name="sensor"))
    d.connect(d.block("sensor"), (obs, "y"))
    d.connect(ctrl, (obs, "u"))
    d.connect(obs, ctrl)

    log = simulate(d, t_max=40.0, dt_control=0.005)
    x = log.col("plant.y", 0)
    settled = np.max(np.abs(x[log.t >= 36.0]))
    open_loop = 1.0 / (C * np.sqrt(K / M))  # 0.25 m uncontrolled at resonance
    assert np.all(np.isfinite(x))
    assert settled < 0.25 * open_loop, "output feedback must beat open loop"
