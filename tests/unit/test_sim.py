"""Unit tests for the block-diagram simulation core."""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.blocks import (
    Gain,
    Harmonic,
    PIDBlock,
    Saturation,
    Select,
    StateFeedback,
    StateSpacePlant,
    Sum,
    sdof_plant,
)
from fuzzy.sim import AlgebraicLoopError, Diagram, WiringError, rk4_step, simulate

M, C, K = 1.0, 0.4, 100.0
OMEGA_N = np.sqrt(K / M)
ZETA = C / (2.0 * np.sqrt(K * M))


def pid_loop(kp: float, ki: float, kd: float, x0: float = 0.1) -> Diagram:
    """Plant + PID, with `Select` splitting the state vector into scalars."""
    d = Diagram()
    plant = sdof_plant(M, C, K, x0=x0)
    pid = PIDBlock(kp, ki, kd, lo=-3.0, hi=3.0, dt=0.005, name="pid")
    pos, vel = Select(0, name="pos"), Select(1, name="vel")
    d.connect(plant, pos)
    d.connect(plant, vel)
    d.connect(pos, (pid, "x"))
    d.connect(vel, (pid, "x_dot"))
    d.connect(pid, plant)
    return d


# ----- integrator -------------------------------------------------------------


def test_rk4_matches_exponential():
    z = np.array([1.0])
    t, h = 0.0, 0.01
    for _ in range(100):
        z = rk4_step(lambda _t, _z: -_z, t, z, h)
        t += h
    assert z[0] == pytest.approx(np.exp(-1.0), abs=1e-9)


def test_rk4_fourth_order_convergence():
    def err(h: float) -> float:
        z, t = np.array([1.0]), 0.0
        for _ in range(int(round(1.0 / h))):
            z = rk4_step(lambda _t, _z: -_z, t, z, h)
            t += h
        return abs(z[0] - np.exp(-1.0))

    # halving the step should cut the error by roughly 2**4
    ratio = err(0.1) / err(0.05)
    assert 10.0 < ratio < 25.0


# ----- scheduling -------------------------------------------------------------


def test_toposort_orders_feedthrough_chain():
    d = Diagram()
    src = Harmonic(name="src")
    g1 = Gain(2.0, name="g1")
    g2 = Gain(3.0, name="g2")
    d.connect(src, g1)
    d.connect(g1, g2)
    out, _ = d.evaluate(np.pi / 2, np.zeros(0))
    assert out[(g2, "y")] == pytest.approx(6.0)


def test_algebraic_loop_raises_and_names_blocks():
    d = Diagram()
    a = Gain(1.0, name="a")
    b = Gain(1.0, name="b")
    d.connect(a, b)
    d.connect(b, a)
    with pytest.raises(AlgebraicLoopError) as exc:
        d.evaluate(0.0, np.zeros(0))
    assert "a" in str(exc.value) and "b" in str(exc.value)
    # structured, so a canvas can highlight the whole loop
    assert exc.value.blocks == ["a", "b"]


# ----- structured error references (what the canvas highlights) ----------------


def test_unconnected_input_names_block_and_port():
    d = Diagram()
    d.add(Gain(1.0, name="g"))
    with pytest.raises(WiringError, match="not connected") as exc:
        d.evaluate(0.0, np.zeros(0))
    assert (exc.value.block, exc.value.port) == ("g", "u")


def test_double_connection_names_the_existing_source():
    """The canvas needs to know which wire is already there, not just that one is."""
    d = Diagram()
    src, other = Harmonic(name="src"), Harmonic(name="other")
    g = Gain(1.0, name="g")
    d.connect(src, g)
    with pytest.raises(WiringError) as exc:
        d.connect(other, g)
    assert (exc.value.block, exc.value.port, exc.value.related) == ("g", "u", "src")


def test_unknown_port_names_block_and_port():
    d = Diagram()
    g = Gain(1.0, name="g")
    with pytest.raises(WiringError) as exc:
        d.connect(Harmonic(name="src"), (g, "nope"))
    assert (exc.value.block, exc.value.port) == ("g", "nope")


def test_ambiguous_port_names_the_block():
    d = Diagram()
    s = Sum(("a", "b"), name="s")
    with pytest.raises(WiringError) as exc:
        d.connect(Harmonic(name="src"), s)
    assert exc.value.block == "s" and exc.value.port is None


def test_duplicate_name_error_names_the_block():
    d = Diagram()
    d.add(Gain(1.0, name="g"))
    with pytest.raises(WiringError, match="duplicate") as exc:
        d.add(Gain(2.0, name="g"))
    assert exc.value.block == "g"


def test_sampled_chain_error_names_both_blocks():
    d = Diagram()
    plant = sdof_plant(M, C, K)
    k1 = StateFeedback([1.0, 0.0], name="k1")
    k2 = StateFeedback([1.0], name="k2")
    d.connect(plant, k1)
    d.connect(k1, k2)
    d.connect(k2, plant)
    with pytest.raises(WiringError, match="multi-rate") as exc:
        d.evaluate(0.0, d.initial_state())
    assert (exc.value.block, exc.value.related) == ("k2", "k1")


def test_feedthrough_plant_in_a_sampled_loop_is_allowed():
    """D != 0 inside a sampled loop is ordinary ZOH structure, not a multi-rate chain.

    The tracer used to walk back through the plant and report a false cycle.
    """
    d = Diagram()
    plant = StateSpacePlant(
        [[0.0, 1.0], [-100.0, -0.4]], [[0.0], [1.0]],
        C=[[1.0, 0.0]], D=[[0.1]], name="plant",
    )
    ctrl = StateFeedback([1.0], name="k")
    d.connect(plant, ctrl)
    d.connect(ctrl, plant)
    d.evaluate(0.0, d.initial_state())  # must not raise


def test_plant_in_loop_is_not_an_algebraic_loop():
    """D == 0 means the plant has no direct feedthrough, so feedback resolves."""
    d = Diagram()
    plant = sdof_plant(M, C, K, x0=0.1)
    ctrl = StateFeedback([1.0, 0.0], name="k")
    d.connect(plant, ctrl)
    d.connect(ctrl, plant)
    d.evaluate(0.0, d.initial_state())  # must not raise


# ----- plant physics ----------------------------------------------------------


def test_sdof_eigenvalues_match_zeta_and_omega_n():
    eig = sdof_plant(M, C, K).eigenvalues()
    assert np.real(eig[0]) == pytest.approx(-ZETA * OMEGA_N, rel=1e-12)
    assert abs(np.imag(eig[0])) == pytest.approx(
        OMEGA_N * np.sqrt(1 - ZETA**2), rel=1e-12
    )


def test_free_decay_envelope_matches_theory():
    from fuzzy.metrics import envelope_decay

    d = Diagram()
    plant = sdof_plant(M, C, K, x0=0.1)
    d.connect(Harmonic(amplitude=0.0, name="none"), plant)
    log = simulate(d, t_max=20.0, dt_control=0.002)
    rate = envelope_decay(log.t, log.col("plant.y", 0))
    assert rate == pytest.approx(ZETA * OMEGA_N, rel=1e-3)


def test_resonant_amplitude_matches_analytic():
    """Steady-state amplitude at resonance is F0 / (c * omega_n)."""
    d = Diagram()
    plant = sdof_plant(M, C, K)
    force = Harmonic(amplitude=1.0, omega=OMEGA_N, name="force")
    d.connect(force, plant)
    log = simulate(d, t_max=200.0, dt_control=0.005)
    peak = np.max(np.abs(log.col("plant.y", 0)[log.t >= 180.0]))
    assert peak == pytest.approx(1.0 / (C * OMEGA_N), rel=1e-3)


def test_closed_loop_eigenvalues_shift_with_state_feedback():
    """u = -(k1 x + k2 v) must move poles exactly like added stiffness/damping."""
    k1, k2 = 84.8, 8.48
    A_cl = np.array([[0.0, 1.0], [-(K + k1) / M, -(C + k2) / M]])
    expected = np.sort_complex(np.linalg.eigvals(A_cl))
    plant = sdof_plant(M, C, K)
    A_eff = plant.A - plant.B @ np.array([[k1, k2]])
    assert np.allclose(np.sort_complex(np.linalg.eigvals(A_eff)), expected)


# ----- state layout and reset -------------------------------------------------


def test_state_vector_concatenates_block_states():
    d = Diagram()
    p1 = sdof_plant(M, C, K, x0=0.1, name="p1")
    p2 = sdof_plant(M, C, K, x0=0.2, name="p2")
    d.connect(Harmonic(amplitude=0.0, name="z1"), p1)
    d.connect(Harmonic(amplitude=0.0, name="z2"), p2)
    assert d.n_states == 4
    assert d.initial_state().tolist() == [0.1, 0.0, 0.2, 0.0]


def test_reset_clears_sampled_state_between_runs():
    """Reusing a diagram across a sweep must not leak held values."""
    d = pid_loop(30.0, 5.0, 10.0)
    first = simulate(d, t_max=2.0, dt_control=0.005)
    second = simulate(d, t_max=2.0, dt_control=0.005)
    assert np.allclose(first["pid.u"], second["pid.u"])


def test_select_extracts_state_components():
    d = pid_loop(30.0, 5.0, 10.0, x0=0.1)
    log = simulate(d, t_max=1.0, dt_control=0.005)
    assert np.allclose(log["pos.y"], log.col("plant.y", 0))
    assert np.allclose(log["vel.y"], log.col("plant.y", 1))


# ----- sampled-block semantics ------------------------------------------------


def test_zero_order_hold_freezes_output_across_interval():
    """The held command must be invariant to the `t` and `z` RK4 probes it with."""
    d = Diagram()
    plant = sdof_plant(M, C, K, x0=0.1)
    ctrl = StateFeedback([10.0, 1.0], name="k")
    d.connect(plant, ctrl)
    d.connect(ctrl, plant)
    z = d.initial_state()
    d.reset()
    d.sample(0.0, z)
    held = d.evaluate(0.0, z)[0][(ctrl, "u")]

    assert held == pytest.approx(-(10.0 * z[0] + 1.0 * z[1]))
    for t, dz in [(0.001, 0.0), (0.0025, 0.05), (0.005, -0.2)]:
        assert d.evaluate(t, z + dz)[0][(ctrl, "u")] == held

    d.sample(0.005, z + 0.1)  # a fresh sample *must* move it
    assert d.evaluate(0.005, z + 0.1)[0][(ctrl, "u")] != held


def test_substeps_do_not_change_control_rate():
    d = Diagram()
    plant = sdof_plant(M, C, K, x0=0.1)
    ctrl = StateFeedback([10.0, 1.0], name="k")
    d.connect(plant, ctrl)
    d.connect(ctrl, plant)
    log = simulate(d, t_max=1.0, dt_control=0.05, n_substeps=4)
    assert len(log.t) == 21
    assert np.allclose(np.diff(log.t), 0.05)


def test_pid_anti_windup_bounds_output():
    """Aggressive gains drive deep saturation; the output must still respect it."""
    log = simulate(pid_loop(500.0, 200.0, 5.0, x0=1.0), t_max=5.0, dt_control=0.005)
    assert np.max(np.abs(log["pid.u"])) == pytest.approx(3.0)
    assert np.max(np.abs(log["pid.u"])) <= 3.0 + 1e-12


def test_saturation_clips():
    d = Diagram()
    sat = Saturation(-1.0, 1.0, name="sat")
    d.connect(Harmonic(amplitude=5.0, omega=1.0, name="src"), sat)
    log = simulate(d, t_max=10.0, dt_control=0.01)
    assert np.max(log["sat.y"]) == pytest.approx(1.0)
    assert np.min(log["sat.y"]) == pytest.approx(-1.0)


def test_sum_applies_signs():
    d = Diagram()
    s = Sum(("a", "b"), signs=(1.0, -1.0), name="s")
    d.connect(Harmonic(amplitude=0.0, name="zero"), (s, "b"))
    d.connect(Harmonic(amplitude=2.0, omega=1.0, name="src"), (s, "a"))
    out, _ = d.evaluate(np.pi / 2, np.zeros(0))
    assert out[(s, "y")] == pytest.approx(2.0)


# ----- analysis ---------------------------------------------------------------


def test_slowest_tau_matches_plant_decay():
    d = Diagram()
    plant = sdof_plant(M, C, K)
    d.connect(Harmonic(amplitude=0.0, name="zero"), plant)
    assert d.slowest_tau() == pytest.approx(1.0 / (ZETA * OMEGA_N), rel=1e-12)


def test_stability_limit_matches_rk4_theory():
    """RK4 is stable while |lambda*h| < 2sqrt(2) on the imaginary axis."""
    d = Diagram()
    d.connect(Harmonic(amplitude=0.0, name="zero"), sdof_plant(M, 0.0, K))
    assert d.fastest_mode() == pytest.approx(OMEGA_N)
    assert d.stability_limit() == pytest.approx(2 * np.sqrt(2) / OMEGA_N)


def test_simulate_warns_above_the_stability_limit():
    """An unstable step overflows to inf silently; the warning is the only signal."""
    d = Diagram()
    d.connect(Harmonic(amplitude=0.0, name="zero"), sdof_plant(M, 0.0, K, x0=0.1))
    with pytest.warns(UserWarning, match="exceeds the RK4 stability limit"):
        with np.errstate(all="ignore"):
            simulate(d, t_max=2.0, dt_control=0.35)


def test_substeps_can_rescue_an_unstable_control_rate():
    d = Diagram()
    d.connect(Harmonic(amplitude=0.0, name="zero"), sdof_plant(M, 0.0, K, x0=0.1))
    log = simulate(d, t_max=2.0, dt_control=0.35, n_substeps=2)  # must not warn
    assert np.all(np.isfinite(log.col("plant.y", 0)))


def test_stability_limit_is_none_without_lti_blocks():
    d = Diagram()
    d.connect(Harmonic(name="src"), Gain(1.0, name="g"))
    assert d.stability_limit() is None
    assert d.fastest_mode() is None


def test_slowest_tau_is_none_without_lti_blocks():
    d = Diagram()
    d.connect(Harmonic(name="src"), Gain(1.0, name="g"))
    assert d.slowest_tau() is None


def test_to_mermaid_lists_blocks_and_edges():
    d = Diagram()
    plant = sdof_plant(M, C, K)
    ctrl = StateFeedback([1.0, 0.0], name="k")
    d.connect(plant, ctrl)
    d.connect(ctrl, plant)
    text = d.to_mermaid()
    assert text.startswith("flowchart LR")
    assert "plant --> k" in text and "k --> plant" in text


def test_feedthrough_flag_follows_D_matrix():
    assert not StateSpacePlant([[0.0]], [[1.0]]).feedthrough
    assert StateSpacePlant([[0.0]], [[1.0]], D=[[1.0]]).feedthrough
