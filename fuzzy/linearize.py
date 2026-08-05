"""Linearize a block about an operating point.

A block's equations are `x' = f(t, x, u)`, `y = g(t, x, u)`. Around an operating
point `(x0, u0)` the small-signal behaviour is the LTI system

    dx' = A dx + B du,    dy = C dx + D du

with `A = ∂f/∂x`, `B = ∂f/∂u`, `C = ∂g/∂x`, `D = ∂g/∂u`, all evaluated at
`(x0, u0)`. This is Ogata's "linearization of nonlinear mathematical models"
(*Modern Control Engineering*, 5th ed., §2-7): expand in a Taylor series about
the operating point and keep the first-order term, valid for signals small
enough that the neglected terms stay small.

The Jacobians are taken numerically, by central differences, because a block is
Python code rather than a symbolic expression. That buys generality — it works
on any block, including one whose `derivative` calls a fuzzy inference engine —
at the cost of needing a step size and of being blind to the difference between
a curve and a corner. §"Corners" below is about the second problem, which is the
one that produces confidently wrong answers.

**Corners.** Ogata's derivation assumes `f` is differentiable at the operating
point. Several blocks here are not: `Saturation` clips, `MotorPlant` rate-limits
`omega'` and clamps both states, `PIDBlock` saturates. At such a point the
one-sided slopes differ, a central difference silently returns their average,
and the resulting model matches the plant in *neither* direction. Every
linearization therefore probes the one-sided slopes too and reports the
coordinates where they disagree, in `Linearization.warnings`. A caller that
ignores them gets a model of a corner.

**Sampled blocks.** A `discrete` block holds its output between control
instants, so `output()` alone does not depend on `u` at all — the dependence is
inside `update()`. For those, the map linearized is `u -> update(); output()`,
driven on a deep copy so the block's own held state is untouched. For a
`FISBlock` that yields the local slope of the fuzzy control surface: the gain
the fuzzy controller is applying *right here*, which is the number to compare
against a state-feedback `K`.

See `docs/implementation-linearization.md`.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from fuzzy.blocks import Block, Inputs

# Central differences are most accurate near eps^(1/3); the factor multiplies a
# per-coordinate scale so the step is relative for large values and absolute
# near zero.
REL_STEP = float(np.cbrt(np.finfo(float).eps))

# A smooth `f` has one-sided slopes agreeing to O(h) ~ 1e-5; a corner makes them
# differ by O(1). Anything above this is a corner, not rounding.
CORNER_TOL = 1e-3


class LinearizationError(Exception):
    """Raised when a block cannot be linearized at all."""

    def __init__(self, message: str, block: str | None = None) -> None:
        super().__init__(message)
        self.block = block


@dataclass(frozen=True)
class Linearization:
    """The LTI model of one block about one operating point."""

    block: str
    A: NDArray[np.float64]
    B: NDArray[np.float64]
    C: NDArray[np.float64]
    D: NDArray[np.float64]
    x0: NDArray[np.float64]
    u0: NDArray[np.float64]
    y0: NDArray[np.float64]
    inputs: tuple[str, ...]      # flat labels, one per column of B and D
    outputs: tuple[str, ...]     # flat labels, one per row of C and D
    warnings: tuple[str, ...]

    @property
    def n_states(self) -> int:
        return int(self.A.shape[0])

    def eigenvalues(self) -> NDArray[np.complex128]:
        """Poles of the linearized model — its local stability."""
        if not self.n_states:
            return np.array([], dtype=np.complex128)
        # `eigvals` narrows to a real dtype for a symmetric-looking A; the caller
        # plots these on the s-plane and wants a complex array either way.
        return np.asarray(np.linalg.eigvals(self.A), dtype=np.complex128)


# ----- port flattening ---------------------------------------------------------
#
# Ports carry scalars or arrays and are addressed by name; A/B/C/D need a flat
# vector. These convert between the two, keeping the port's original shape so a
# block that unpacks `u["u"]` as a vector still receives a vector.


def _labels(order: tuple[str, ...], sizes: tuple[int, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for name, n in zip(order, sizes, strict=True):
        out.extend([name] if n == 1 else [f"{name}[{i}]" for i in range(n)])
    return tuple(out)


def _sizes(mapping: Inputs, order: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(
        int(np.asarray(mapping[k], dtype=float).size) for k in order
    )


def _flat(mapping: Inputs, order: tuple[str, ...]) -> NDArray[np.float64]:
    if not order:
        return np.zeros(0)
    return np.concatenate(
        [np.atleast_1d(np.asarray(mapping[k], dtype=float)).ravel() for k in order]
    )


def _rebuild(
    vec: NDArray[np.float64], order: tuple[str, ...], template: Inputs
) -> dict[str, Any]:
    """Flat vector back into a port mapping shaped like `template`."""
    out: dict[str, Any] = {}
    i = 0
    for name in order:
        ref = np.asarray(template[name], dtype=float)
        n = int(ref.size)
        chunk = vec[i : i + n]
        i += n
        out[name] = float(chunk[0]) if ref.ndim == 0 else chunk.reshape(ref.shape)
    return out


# ----- differentiation ----------------------------------------------------------


def _jacobian(
    f: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    v0: NDArray[np.float64],
    n_rows: int,
) -> tuple[NDArray[np.float64], list[int]]:
    """Central-difference Jacobian, plus the coordinates where `f` has a corner.

    The corner test costs one extra evaluation of `f` in total: with `f(v0)`
    known, the forward and backward slopes fall out of the same two evaluations
    the central difference already needs.
    """
    J = np.zeros((n_rows, v0.size))
    corners: list[int] = []
    if not v0.size:
        return J, corners

    f0 = np.atleast_1d(np.asarray(f(v0), dtype=float)).ravel()
    for j in range(v0.size):
        h = REL_STEP * max(abs(float(v0[j])), 1.0)
        vp = v0.copy()
        vp[j] += h
        vm = v0.copy()
        vm[j] -= h
        fp = np.atleast_1d(np.asarray(f(vp), dtype=float)).ravel()
        fm = np.atleast_1d(np.asarray(f(vm), dtype=float)).ravel()
        J[:, j] = (fp - fm) / (2.0 * h)

        forward = (fp - f0) / h
        backward = (f0 - fm) / h
        scale = 1.0 + np.abs(J[:, j])
        if np.any(np.abs(forward - backward) > CORNER_TOL * scale):
            corners.append(j)
    return J, corners


def _degenerate_warnings(
    A: NDArray[np.float64],
    B: NDArray[np.float64],
    C: NDArray[np.float64],
    D: NDArray[np.float64],
    out_labels: tuple[str, ...],
    responsive: bool,
) -> list[str]:
    """Rows that vanish entirely — the quiet half of the limiter problem.

    Deep inside a saturated region a limiter *is* differentiable, with slope
    zero, so the corner test says nothing and the Jacobian comes back correct
    and useless: a row of zeros means that state cannot be moved from here, and
    a Bode plot of it is a flat line that looks like a result. Worth saying out
    loud, since the arithmetic gives no hint.
    """
    out: list[str] = []
    for i in range(A.shape[0]):
        if not A[i].any() and not B[i].any():
            out.append(
                f"state x[{i}] cannot move at this operating point — its row of "
                f"both A and B is zero, which is what a saturated rate limit or a "
                f"state sitting against its clamp looks like. The linear model "
                f"says this state is frozen; the block is merely limited here."
            )
    if responsive:
        for i in range(C.shape[0]):
            if not C[i].any() and not D[i].any():
                out.append(
                    f"output {out_labels[i]} does not respond to any state or "
                    f"input at this operating point — the block is clipped flat "
                    f"here, so its linear model carries no dynamics at all."
                )
    return out


def _corner_warnings(
    what: str, corners: list[int], labels: tuple[str, ...]
) -> list[str]:
    if not corners:
        return []
    named = ", ".join(labels[j] for j in corners)
    return [
        f"{what} is not differentiable in {named} at this operating point — a "
        f"limiter or clamp is active there, so the slope differs either side and "
        f"the linear model matches the block in neither direction."
    ]


# ----- the public entry point ----------------------------------------------------


def linearize(
    block: Block,
    x0: NDArray[np.float64] | None = None,
    u0: Inputs | None = None,
    t: float = 0.0,
) -> Linearization:
    """LTI model of `block` about `(x0, u0)` at time `t`.

    `x0` defaults to the block's own `initial_state()`, `u0` to zero on every
    input port. A block whose input port carries a *vector* has no way to say so
    — `Select` takes a whole state vector — so `u0` must name that port
    explicitly with an array of the right length.

    `t` matters only for a block that reads it (`Step`, `Harmonic`); those have
    no `x` or `u` dependence at all and linearize to the zero system, which is
    correct: a source contributes no small-signal dynamics.
    """
    name = block.name
    if block.n_states and not hasattr(type(block), "derivative"):
        raise LinearizationError(f"block {name!r} has states but no derivative", name)

    x0 = (
        np.asarray(block.initial_state(), dtype=float).ravel()
        if x0 is None
        else np.asarray(x0, dtype=float).ravel()
    )
    if x0.size != block.n_states:
        raise LinearizationError(
            f"block {name!r} takes {block.n_states} states, got {x0.size}", name
        )

    order = tuple(block.inputs)
    nominal: dict[str, Any] = {k: 0.0 for k in order}
    nominal.update({k: v for k, v in (u0 or {}).items() if k in order})
    missing = [k for k in (u0 or {}) if k not in order]
    if missing:
        raise LinearizationError(
            f"block {name!r} has no input port {missing[0]!r}", name
        )
    u_vec = _flat(nominal, order)
    in_labels = _labels(order, _sizes(nominal, order))

    # A sampled block's dependence on `u` lives in `update()`, not `output()`.
    # Drive a copy so the real block's held value survives the probing.
    probe = copy.deepcopy(block) if block.discrete else block

    def emit(u_map: Inputs, x: NDArray[np.float64]) -> dict[str, Any]:
        if probe.discrete:
            probe.update(t, u_map)
        return probe.output(t, x, u_map)

    y_map = emit(nominal, x0)
    out_order = tuple(block.outputs)
    y_vec = _flat(y_map, out_order)
    out_labels = _labels(out_order, _sizes(y_map, out_order))
    n_out = y_vec.size

    def g_of_x(x: NDArray[np.float64]) -> NDArray[np.float64]:
        return _flat(emit(nominal, x), out_order)

    def g_of_u(uv: NDArray[np.float64]) -> NDArray[np.float64]:
        return _flat(emit(_rebuild(uv, order, nominal), x0), out_order)

    warnings: list[str] = []
    C, corners = _jacobian(g_of_x, x0, n_out)
    warnings += _corner_warnings("`output`", corners, _labels(("x",), (x0.size,)))
    D, corners = _jacobian(g_of_u, u_vec, n_out)
    warnings += _corner_warnings("`output`", corners, in_labels)

    if block.n_states:

        def f_of_x(x: NDArray[np.float64]) -> NDArray[np.float64]:
            return np.asarray(block.derivative(t, x, nominal), dtype=float).ravel()

        def f_of_u(uv: NDArray[np.float64]) -> NDArray[np.float64]:
            u_map = _rebuild(uv, order, nominal)
            return np.asarray(block.derivative(t, x0, u_map), dtype=float).ravel()

        state_labels = _labels(("x",), (x0.size,))
        A, corners = _jacobian(f_of_x, x0, block.n_states)
        warnings += _corner_warnings("`derivative`", corners, state_labels)
        B, corners = _jacobian(f_of_u, u_vec, block.n_states)
        warnings += _corner_warnings("`derivative`", corners, in_labels)
    else:
        A = np.zeros((0, 0))
        B = np.zeros((0, u_vec.size))

    # A pure source (no inputs, no states) is *supposed* to have a dead output;
    # only a block that had something to respond to is worth flagging.
    warnings += _degenerate_warnings(
        A, B, C, D, out_labels, responsive=bool(order or block.n_states)
    )

    return Linearization(
        block=name, A=A, B=B, C=C, D=D,
        x0=x0, u0=u_vec, y0=y_vec,
        inputs=in_labels, outputs=out_labels,
        warnings=tuple(warnings),
    )


def equilibrium(
    block: Block,
    u0: Inputs | None = None,
    x_guess: NDArray[np.float64] | None = None,
    t: float = 0.0,
    tol: float = 1e-10,
    max_iter: int = 50,
) -> tuple[NDArray[np.float64], float]:
    """Solve `f(t, x, u0) = 0` for `x` by Newton's method from `x_guess`.

    Returns `(x, residual)`. The residual is the caller's to check: not every
    block has an equilibrium at a given `u0` (a pure integrator driven off zero
    has none), and a Newton iteration that cannot converge still has to return
    something rather than raise.

    The step is a least-squares solve rather than an inverse, because `∂f/∂x` is
    routinely singular here — `MotorPlant`'s voltage state is an integrator, so
    its equilibria form a line rather than a point, and the minimum-norm step is
    the one that stays nearest the guess.
    """
    n = block.n_states
    if not n:
        return np.zeros(0), 0.0

    order = tuple(block.inputs)
    nominal: dict[str, Any] = {k: 0.0 for k in order}
    nominal.update({k: v for k, v in (u0 or {}).items() if k in order})

    x = (
        np.asarray(block.initial_state(), dtype=float).ravel()
        if x_guess is None
        else np.asarray(x_guess, dtype=float).ravel()
    )

    def f(v: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray(block.derivative(t, v, nominal), dtype=float).ravel()

    residual = float(np.linalg.norm(f(x)))
    for _ in range(max_iter):
        if residual <= tol:
            break
        J, _ = _jacobian(f, x, n)
        step, *_ = np.linalg.lstsq(J, -f(x), rcond=None)
        if not np.all(np.isfinite(step)):
            break
        x_next = x + step
        r_next = float(np.linalg.norm(f(x_next)))
        if r_next >= residual:      # not converging; keep the better point
            break
        x, residual = x_next, r_next
    return x, residual


# ----- the whole diagram --------------------------------------------------------


def _named(out: dict[Any, Any]) -> dict[str, Any]:
    """`evaluate()`'s `(block, port)` keys as the `"block.port"` names used here."""
    return {f"{b.name}.{port}": value for (b, port), value in out.items()}


def linearize_diagram(
    diagram: Any,
    z0: NDArray[np.float64] | None = None,
    t: float = 0.0,
    inputs: Sequence[str] | None = None,
    outputs: Sequence[str] | None = None,
) -> Linearization:
    """The whole diagram as one LTI model — the **closed loop**, not a block.

    `A = ∂ż/∂z` over the diagram's concatenated state vector, so its eigenvalues
    are the closed-loop poles: whether this controller stabilizes this plant, and
    with what damping. That is the question a per-block linearization cannot
    answer, because it has the loop cut at every wire.

    A closed diagram has no free input ports — every one is wired — so `B` and
    `D` come from *injecting* a perturbation onto a named signal (§`Diagram.
    evaluate`). `inputs` defaults to the diagram's source signals, which is where
    a disturbance or a reference actually enters; `outputs` defaults to every
    signal the diagram produces.

    **Sampled blocks are treated as instantaneous.** A `discrete` block's
    `output()` returns a value held from the last control instant, so leaving it
    alone would linearize the loop as though it were cut at the controller — the
    poles would be the plant's, and the controller would appear to do nothing. It
    is therefore re-sampled at every probe, which models the zero-order hold by
    its continuous equivalent and **ignores the sampling delay**. That is the
    standard fast-sampling approximation and it is optimistic: a real ZOH adds
    roughly `dt/2` of phase lag, so a loop that looks marginally stable here may
    not be. The returned `warnings` say so whenever the diagram has one.

    The diagram is deep-copied first: re-sampling mutates the held values, and
    probing a Jacobian must not disturb the caller's diagram.
    """
    probe = copy.deepcopy(diagram)
    z0 = (
        np.asarray(probe.initial_state(), dtype=float).ravel()
        if z0 is None
        else np.asarray(z0, dtype=float).ravel()
    )
    if z0.size != probe.n_states:
        raise LinearizationError(
            f"diagram takes {probe.n_states} states, got {z0.size}"
        )

    known = set(probe.signal_names())
    in_names = tuple(probe.source_signals() if inputs is None else inputs)
    out_names = tuple(probe.signal_names() if outputs is None else outputs)
    for name in in_names + out_names:
        if name not in known:
            raise LinearizationError(f"no signal {name!r} in this diagram")

    def evaluate(z: NDArray[np.float64], inj: dict[str, Any] | None) -> dict[str, Any]:
        probe.sample(t, z, inj)
        out, _ = probe.evaluate(t, z, inj)
        return _named(out)

    nominal = evaluate(z0, None)
    zero_inj = {n: np.zeros_like(np.atleast_1d(np.asarray(nominal[n], dtype=float)))
                for n in in_names}
    d_vec = _flat(zero_inj, in_names)
    in_labels = _labels(in_names, _sizes(zero_inj, in_names))
    out_labels = _labels(out_names, _sizes(nominal, out_names))
    y0 = _flat(nominal, out_names)

    def g_of_z(z: NDArray[np.float64]) -> NDArray[np.float64]:
        return _flat(evaluate(z, None), out_names)

    def g_of_d(d: NDArray[np.float64]) -> NDArray[np.float64]:
        return _flat(evaluate(z0, _rebuild(d, in_names, zero_inj)), out_names)

    def f_of_z(z: NDArray[np.float64]) -> NDArray[np.float64]:
        probe.sample(t, z)
        return np.asarray(probe.derivative(t, z), dtype=float).ravel()

    def f_of_d(d: NDArray[np.float64]) -> NDArray[np.float64]:
        inj = _rebuild(d, in_names, zero_inj)
        probe.sample(t, z0, inj)
        return np.asarray(probe.derivative(t, z0, inj), dtype=float).ravel()

    state_labels = _labels(("z",), (z0.size,))
    warnings: list[str] = []
    A, corners = _jacobian(f_of_z, z0, probe.n_states)
    warnings += _corner_warnings("the diagram's derivative", corners, state_labels)
    B, corners = _jacobian(f_of_d, d_vec, probe.n_states)
    warnings += _corner_warnings("the diagram's derivative", corners, in_labels)
    C, corners = _jacobian(g_of_z, z0, y0.size)
    warnings += _corner_warnings("the diagram's outputs", corners, state_labels)
    D, corners = _jacobian(g_of_d, d_vec, y0.size)
    warnings += _corner_warnings("the diagram's outputs", corners, in_labels)

    if any(b.discrete for b in probe.blocks):
        held = ", ".join(b.name for b in probe.blocks if b.discrete)
        warnings.append(
            f"{held} is sampled and held; this model replaces it with its "
            f"continuous equivalent and ignores the sampling delay. A real "
            f"zero-order hold adds about dt/2 of phase lag, so these poles are "
            f"optimistic — a loop that looks marginally stable here may not be."
        )

    return Linearization(
        block=getattr(probe, "name", "diagram"),
        A=A, B=B, C=C, D=D,
        x0=z0, u0=d_vec, y0=y0,
        inputs=in_labels, outputs=out_labels,
        warnings=tuple(warnings),
    )
