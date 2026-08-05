"""Linearization checked against Jacobians worked out by hand.

The numerical Jacobian is only worth having if it reproduces the analytic one on
the cases where the analytic one is known, and if it says so when the block has
a corner instead of a slope. Both halves are pinned here.
"""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.blocks import (
    Constant,
    FISBlock,
    Gain,
    Harmonic,
    MotorPlant,
    Saturation,
    Select,
    StateSpacePlant,
    Sum,
    sdof_plant,
)
from fuzzy.linearize import (
    LinearizationError,
    equilibrium,
    linearize,
    linearize_diagram,
)
from fuzzy.sim import Diagram
from fuzzy.spec import load

EX2 = "exercises/exercicio2_sdof_vibration_control/diagram.json"


def motor(**kw) -> MotorPlant:
    """A motor with the limiter wide open unless a test narrows it."""
    args = dict(
        k=10.0, omega_rate_max=1e9, omega_bounds=(0.0, 1000.0),
        v_bounds=(0.0, 100.0), omega0=500.0, v0=50.0,
    )
    args.update(kw)
    return MotorPlant(**args)


# ----- exactness on the cases with a closed form ---------------------------------


def test_an_lti_block_linearizes_back_to_itself():
    """`x' = Ax+Bu` is its own linearization, to the last bit."""
    p = sdof_plant(m=1.0, c=0.4, k=100.0)
    lin = linearize(p, u0={"u": 0.0})
    assert np.array_equal(lin.A, p.A)
    assert np.array_equal(lin.B, p.B)
    assert np.array_equal(lin.C, p.C)
    assert np.array_equal(lin.D, p.D)
    assert lin.warnings == ()


def test_the_motor_matches_its_hand_computed_jacobian():
    """`omega' = k V - omega`, `V' = u`, `y = [omega, V]` away from every limit."""
    lin = linearize(motor(), u0={"u": 0.0})
    assert np.allclose(lin.A, [[-1.0, 10.0], [0.0, 0.0]])
    assert np.allclose(lin.B, [[0.0], [1.0]])
    assert np.allclose(lin.C, np.eye(2))
    assert np.allclose(lin.D, [[0.0], [0.0]])
    # one real mode plus the free integrator on the voltage state
    assert sorted(np.real(lin.eigenvalues())) == pytest.approx([-1.0, 0.0])


def test_an_algebraic_block_has_no_states_only_a_gain():
    lin = linearize(Gain(k=3.0), u0={"u": 0.0})
    assert lin.n_states == 0
    assert lin.A.shape == (0, 0)
    assert np.allclose(lin.D, [[3.0]])


def test_ports_are_labelled_flat():
    """A vector port becomes one labelled column per component."""
    lin = linearize(motor(), u0={"u": 0.0})
    assert lin.inputs == ("u",)
    assert lin.outputs == ("y[0]", "y[1]")


def test_a_vector_input_port_needs_a_nominal_of_the_right_length():
    """`Select` takes a whole state vector; nothing in the class says how long."""
    lin = linearize(Select(index=1), u0={"u": np.zeros(3)})
    assert lin.inputs == ("u[0]", "u[1]", "u[2]")
    assert np.allclose(lin.D, [[0.0, 1.0, 0.0]])


# ----- corners, where the linear model is a lie -----------------------------------


def test_a_corner_is_reported_not_averaged():
    """At the clip point the slope is 1 on one side and 0 on the other; a central
    difference reports 0.5, which matches the block in neither direction."""
    lin = linearize(Saturation(lo=-1.0, hi=1.0), u0={"u": 1.0})
    assert np.allclose(lin.D, [[0.5]])
    assert any("not differentiable" in w for w in lin.warnings)


def test_no_warning_where_the_block_really_is_smooth():
    assert linearize(Saturation(lo=-1.0, hi=1.0), u0={"u": 0.0}).warnings == ()
    assert linearize(motor(), u0={"u": 0.0}).warnings == ()


def test_a_state_against_its_clamp_is_reported():
    lin = linearize(motor(omega0=0.0), u0={"u": 0.0})   # omega on its lower bound
    assert any("not differentiable" in w for w in lin.warnings)


def test_a_saturated_rate_limit_is_reported_even_though_it_is_smooth():
    """Deep inside saturation the slope is a perfectly well-defined zero, so the
    corner test stays silent — and the model quietly claims the state is frozen."""
    lin = linearize(motor(omega_rate_max=1.0, omega0=100.0), u0={"u": 0.0})
    assert np.allclose(lin.A[0], [0.0, 0.0])
    assert not any("not differentiable" in w for w in lin.warnings)
    assert any("cannot move" in w for w in lin.warnings)


def test_a_fully_clipped_block_is_reported_as_carrying_no_dynamics():
    lin = linearize(Saturation(lo=-1.0, hi=1.0), u0={"u": 5.0})
    assert np.allclose(lin.D, [[0.0]])
    assert any("does not respond" in w for w in lin.warnings)


def test_a_pure_source_is_not_scolded_for_having_a_constant_output():
    """A source has nothing to respond to; a warning there would be noise."""
    assert linearize(Constant(3.0)).warnings == ()
    assert linearize(Harmonic(1.0, 2.0, 0.0)).warnings == ()


# ----- sampled blocks -------------------------------------------------------------


def test_a_fuzzy_controller_linearizes_to_its_local_gain():
    """The slope of the control surface at a point — the fuzzy controller's
    equivalent `K` right there, which is the number a linear design compares to."""
    fis = next(b for b in load(EX2).blocks if isinstance(b, FISBlock))
    at_rest = linearize(fis, u0={"deslocamento": 0.0, "velocidade": 0.0})
    assert at_rest.inputs == ("deslocamento", "velocidade")
    assert at_rest.D.shape == (1, 2)
    # a stabilising controller opposes displacement and velocity
    assert at_rest.D[0, 0] < 0 and at_rest.D[0, 1] < 0


def test_the_local_gain_changes_with_the_operating_point():
    """If it did not, the controller would be linear and the fuzz pointless."""
    fis = next(b for b in load(EX2).blocks if isinstance(b, FISBlock))
    a = linearize(fis, u0={"deslocamento": 0.0, "velocidade": 0.0}).D
    b = linearize(fis, u0={"deslocamento": 0.02, "velocidade": 0.0}).D
    assert not np.allclose(a, b)


def test_probing_a_sampled_block_does_not_disturb_its_held_output():
    """It is driven through `update()`, which is exactly the mutation to avoid."""
    fis = next(b for b in load(EX2).blocks if isinstance(b, FISBlock))
    fis.update(0.0, {"deslocamento": 0.05, "velocidade": 0.0})
    held = fis._held
    linearize(fis, u0={"deslocamento": 0.0, "velocidade": 0.0})
    assert fis._held == held


# ----- equilibrium ----------------------------------------------------------------


def test_equilibrium_finds_the_nearest_point_of_the_manifold():
    """`omega' = 0` needs `omega = k V`, a line rather than a point, so the
    minimum-norm Newton step lands on its closest point to the guess."""
    m = motor(omega0=0.0, v0=50.0)
    x, residual = equilibrium(m, u0={"u": 0.0}, x_guess=[0.0, 50.0])
    assert residual < 1e-9
    assert x[0] == pytest.approx(10.0 * x[1])          # on the manifold
    # closest point of `omega = 10 V` to (0, 50): V = 500/1010
    assert x[1] == pytest.approx(500.0 / 1010.0, rel=1e-6)


def test_equilibrium_reports_a_residual_when_there_is_none():
    """Driving the voltage integrator off zero leaves `V' = u != 0` forever."""
    _, residual = equilibrium(motor(), u0={"u": 2.0}, x_guess=[500.0, 50.0])
    assert residual == pytest.approx(2.0)


def test_equilibrium_of_an_algebraic_block_is_empty():
    x, residual = equilibrium(Gain(k=2.0), u0={"u": 1.0})
    assert x.size == 0 and residual == 0.0


# ----- error paths ----------------------------------------------------------------


def test_a_wrong_length_state_is_refused():
    with pytest.raises(LinearizationError, match="takes 2 states"):
        linearize(motor(), x0=[1.0])


def test_an_unknown_port_is_refused():
    """Silently ignoring it would linearize about a different point than asked."""
    with pytest.raises(LinearizationError, match="no input port"):
        linearize(motor(), u0={"nope": 1.0})


# ----- the whole diagram ----------------------------------------------------------


def unity_feedback_loop(g: float) -> tuple[Diagram, float, float, float]:
    """`m x'' + c x' + k x = f + g x`, so the loop shifts the stiffness to `k - g`."""
    m, c, k = 1.0, 0.4, 100.0
    d = Diagram("loop")
    plant = sdof_plant(m=m, c=c, k=k)
    total = Sum(("ext", "ctrl"))
    d.connect(Harmonic(1.0, 10.0, 0.0, name="force"), (total, "ext"))
    d.connect(total, plant)
    d.connect(plant, Select(0, name="pos"))
    d.connect(d.block("pos"), Gain(g, name="fb"))
    d.connect(d.block("fb"), (total, "ctrl"))
    return d, m, c, k


def test_the_closed_loop_matrix_matches_the_hand_computed_one():
    d, m, c, k = unity_feedback_loop(-25.0)
    lin = linearize_diagram(d)
    assert np.allclose(lin.A, [[0.0, 1.0], [-(k + 25.0) / m, -c / m]])


def test_the_closed_loop_poles_are_not_the_open_loop_poles():
    """The point of the whole exercise: a per-block linearization has the loop
    cut at every wire and can only ever report the plant's own poles."""
    d, m, c, k = unity_feedback_loop(-25.0)
    closed = np.sort_complex(linearize_diagram(d).eigenvalues())
    assert np.allclose(closed, np.sort_complex(np.roots([m, c, k + 25.0])))
    assert not np.allclose(closed, np.sort_complex(np.roots([m, c, k])))


def test_the_source_signal_is_the_default_input():
    d, m, _, _ = unity_feedback_loop(-25.0)
    lin = linearize_diagram(d)
    assert lin.inputs == ("force.y",)
    assert np.allclose(lin.B, [[0.0], [1.0 / m]])


def test_an_unknown_signal_is_refused():
    d, *_ = unity_feedback_loop(0.0)
    with pytest.raises(LinearizationError, match="no signal"):
        linearize_diagram(d, inputs=["nope.y"])


def test_a_sampled_controller_actually_closes_the_loop():
    """A `discrete` block returns a *held* output, so leaving it alone would
    linearize the loop as though it were cut at the controller: the poles would
    come back as the bare plant's and the controller would look inert."""
    d = load(EX2)
    plant = next(b for b in d.blocks if isinstance(b, StateSpacePlant))
    lin = linearize_diagram(d)

    open_loop = np.linalg.eigvals(plant.A)
    assert not np.allclose(np.sort_complex(lin.eigenvalues()),
                           np.sort_complex(open_loop))

    # the fuzzy controller's local gain, taken independently, reproduces A
    fis = next(b for b in d.blocks if isinstance(b, FISBlock))
    D = linearize(fis, u0={"deslocamento": 0.0, "velocidade": 0.0}).D
    assert np.allclose(lin.A, plant.A + plant.B @ D, atol=1e-6)


def test_the_fuzzy_controller_adds_damping():
    """The research claim, as a number: the loop is better damped than the plant."""
    d = load(EX2)
    plant = next(b for b in d.blocks if isinstance(b, StateSpacePlant))
    zeta = lambda p: float(-np.real(p[0]) / np.abs(p[0]))  # noqa: E731
    assert zeta(np.linalg.eigvals(plant.A)) == pytest.approx(0.02, abs=1e-3)
    assert zeta(linearize_diagram(d).eigenvalues()) > 0.08


def test_the_zero_order_hold_approximation_is_declared():
    """It ignores the sampling delay, which makes the poles optimistic."""
    assert any("sampling delay" in w for w in linearize_diagram(load(EX2)).warnings)


def test_a_continuous_diagram_carries_no_such_caveat():
    d, *_ = unity_feedback_loop(-25.0)
    assert linearize_diagram(d).warnings == ()
