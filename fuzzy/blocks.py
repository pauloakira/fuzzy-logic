"""Blocks for the diagram simulation core.

A block is described by three orthogonal properties, not by a class hierarchy:

- ``n_states`` — 0 for a purely algebraic block, ``n > 0`` for a block carrying
  continuous state that is integrated as part of the diagram's single ODE.
- ``feedthrough`` — whether ``output()`` reads its inputs. ``False`` breaks
  scheduling cycles, which is what lets plant-in-the-loop feedback resolve
  without an algebraic-loop solver.
- ``discrete`` — whether the block is sampled at the control rate and its output
  held constant in between (zero-order hold). Discrete blocks own their state
  internally rather than through the diagram's state vector.

See `docs/design-block-diagram-simulation.md` for the rationale.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from fuzzy.fis import MamdaniFIS

Inputs = Mapping[str, Any]


class Block:
    """Base class. Subclasses set the class attributes and implement `output`."""

    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ("y",)
    n_states: int = 0
    feedthrough: bool = True
    discrete: bool = False

    def __init__(self, name: str | None = None) -> None:
        self.name = name or type(self).__name__.lower()

    def initial_state(self) -> NDArray[np.float64]:
        """Continuous initial state. Length must equal `n_states`."""
        return np.zeros(self.n_states, dtype=float)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        """Block outputs at time `t`. Must not read `u` unless `feedthrough`."""
        raise NotImplementedError

    def derivative(
        self, t: float, x: NDArray[np.float64], u: Inputs
    ) -> NDArray[np.float64]:
        """State derivative. Only called when `n_states > 0`."""
        raise NotImplementedError

    def update(self, t: float, u: Inputs) -> None:
        """Advance internal discrete state. Only called when `discrete`."""
        raise NotImplementedError

    def reset(self) -> None:
        """Clear internal (non-`z`) state. Called at the start of every run."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"


# ----- Sources ---------------------------------------------------------------


class Constant(Block):
    """Constant source."""

    feedthrough = False

    def __init__(self, value: float = 0.0, name: str | None = None) -> None:
        super().__init__(name)
        self.value = float(value)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": self.value}


class Step(Block):
    """Step from `initial` to `final` at `t_step`."""

    feedthrough = False

    def __init__(
        self,
        final: float = 1.0,
        t_step: float = 0.0,
        initial: float = 0.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.final = float(final)
        self.t_step = float(t_step)
        self.initial = float(initial)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": self.final if t >= self.t_step else self.initial}


class Harmonic(Block):
    """`amplitude * sin(omega * t + phase)`.

    `omega` is a plain attribute so a frequency sweep is a loop over the same
    diagram rather than a rebuilt one.
    """

    feedthrough = False

    def __init__(
        self,
        amplitude: float = 1.0,
        omega: float = 1.0,
        phase: float = 0.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.amplitude = float(amplitude)
        self.omega = float(omega)
        self.phase = float(phase)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": self.amplitude * np.sin(self.omega * t + self.phase)}


# ----- Algebraic blocks ------------------------------------------------------


class Gain(Block):
    """Scalar or matrix gain."""

    inputs = ("u",)

    def __init__(self, k: ArrayLike, name: str | None = None) -> None:
        super().__init__(name)
        self.k = np.asarray(k, dtype=float) if np.ndim(k) else float(k)  # type: ignore[arg-type]

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": np.dot(self.k, u["u"]) if np.ndim(self.k) else self.k * u["u"]}


class Sum(Block):
    """Signed sum of named input ports."""

    def __init__(
        self,
        ports: Sequence[str] = ("a", "b"),
        signs: Sequence[float] | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.inputs = tuple(ports)
        self.signs = tuple(signs) if signs is not None else (1.0,) * len(self.inputs)
        if len(self.signs) != len(self.inputs):
            raise ValueError("`signs` must match `ports` in length")

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": sum(s * u[p] for s, p in zip(self.signs, self.inputs))}


class Select(Block):
    """Extract one component of a vector-valued signal.

    Plants emit their full state vector, while controllers take named scalar
    inputs (`x` and `x_dot`, or `deslocamento` and `velocidade`), so a phase-plane
    controller wires up through one `Select` per input.
    """

    inputs = ("u",)

    def __init__(self, index: int, name: str | None = None) -> None:
        super().__init__(name)
        self.index = int(index)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": float(np.atleast_1d(u["u"])[self.index])}


class Saturation(Block):
    """Clip to `[lo, hi]`."""

    inputs = ("u",)

    def __init__(self, lo: float, hi: float, name: str | None = None) -> None:
        super().__init__(name)
        if hi <= lo:
            raise ValueError("`hi` must exceed `lo`")
        self.lo = float(lo)
        self.hi = float(hi)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"y": float(np.clip(u["u"], self.lo, self.hi))}


# ----- Plants ----------------------------------------------------------------


class StateSpacePlant(Block):
    """Continuous LTI plant `x' = A x + B u`, `y = C x + D u`.

    `C` defaults to the identity, so `y` is the full state vector — which is what
    a phase-plane fuzzy controller or a state-feedback law consumes.
    """

    inputs = ("u",)

    def __init__(
        self,
        A: ArrayLike,
        B: ArrayLike,
        C: ArrayLike | None = None,
        D: ArrayLike | None = None,
        x0: ArrayLike | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.A = np.atleast_2d(np.asarray(A, dtype=float))
        self.B = np.asarray(B, dtype=float).reshape(self.A.shape[0], -1)
        n = self.A.shape[0]
        if self.A.shape[1] != n:
            raise ValueError("`A` must be square")
        self.C = np.eye(n) if C is None else np.atleast_2d(np.asarray(C, dtype=float))
        self.D = (
            np.zeros((self.C.shape[0], self.B.shape[1]))
            if D is None
            else np.atleast_2d(np.asarray(D, dtype=float))
        )
        self.x0 = np.zeros(n) if x0 is None else np.asarray(x0, dtype=float).ravel()
        if self.x0.size != n:
            raise ValueError(f"`x0` must have length {n}")
        self.n_states = n
        self.feedthrough = bool(np.any(self.D))

    def initial_state(self) -> NDArray[np.float64]:
        return self.x0.copy()

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        y = self.C @ x
        if self.feedthrough:
            y = y + (self.D @ np.atleast_1d(u["u"])).ravel()
        return {"y": y}

    def derivative(
        self, t: float, x: NDArray[np.float64], u: Inputs
    ) -> NDArray[np.float64]:
        return self.A @ x + (self.B @ np.atleast_1d(u["u"])).ravel()

    def eigenvalues(self) -> NDArray[np.complex128]:
        return np.linalg.eigvals(self.A)


def sdof_plant(
    m: float, c: float, k: float, x0: float = 0.0, v0: float = 0.0, name: str = "plant"
) -> StateSpacePlant:
    """SDOF mass-spring-damper `m x'' + c x' + k x = u`, state `[x, x']`."""
    return StateSpacePlant(
        A=[[0.0, 1.0], [-k / m, -c / m]], B=[[0.0], [1.0 / m]], x0=[x0, v0], name=name
    )


# ----- Controllers (sampled) -------------------------------------------------


class FISBlock(Block):
    """Mamdani FIS as a sampled controller.

    One input port per FIS input variable. `gain` scales each input before it
    reaches the FIS: a gain of 10 is equivalent to a 10x tighter universe of
    discourse, and these are the fuzzy controller's *scaling gains* — the direct
    analogue of the entries of a state-feedback matrix `K`.
    """

    outputs = ("u",)
    discrete = True
    feedthrough = False

    def __init__(
        self,
        fis: MamdaniFIS,
        gain: Mapping[str, float] | None = None,
        clip: Mapping[str, tuple[float, float]] | None = None,
        output_gain: float = 1.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.fis = fis
        self.inputs = tuple(fis.inputs)
        self.gain = dict(gain or {})
        self.clip = dict(clip or {})
        self.output_gain = float(output_gain)
        self._held = 0.0

    def reset(self) -> None:
        self._held = 0.0

    def update(self, t: float, u: Inputs) -> None:
        values = {}
        for var in self.inputs:
            v = float(u[var]) * self.gain.get(var, 1.0)
            if var in self.clip:
                v = float(np.clip(v, *self.clip[var]))
            values[var] = v
        self._held = self.output_gain * self.fis.evaluate(values)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"u": self._held}


class PIDBlock(Block):
    """Sampled PID with derivative-on-output and back-calculation anti-windup.

    `u = kp*e + I - kd*x_dot`, `e = setpoint - x`, saturated to `[lo, hi]`;
    the integrator is corrected toward feasibility with time constant `Tt`.
    Saturation is internal so the anti-windup path needs no feedback wire.
    """

    inputs = ("x", "x_dot")
    outputs = ("u",)
    discrete = True
    feedthrough = False

    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        lo: float = -np.inf,
        hi: float = np.inf,
        Tt: float = 1.0,
        setpoint: float = 0.0,
        dt: float = 0.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.kp, self.ki, self.kd = float(kp), float(ki), float(kd)
        self.lo, self.hi = float(lo), float(hi)
        self.Tt = float(Tt)
        self.setpoint = float(setpoint)
        self.dt = float(dt)
        self._integral = 0.0
        self._held = 0.0

    def reset(self) -> None:
        self._integral = 0.0
        self._held = 0.0

    def update(self, t: float, u: Inputs) -> None:
        e = self.setpoint - float(u["x"])
        unsat = self.kp * e + self._integral - self.kd * float(u["x_dot"])
        sat = float(np.clip(unsat, self.lo, self.hi))
        self._held = sat
        if self.dt > 0.0:
            self._integral += self.dt * (self.ki * e + (sat - unsat) / self.Tt)

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"u": self._held}


class StateFeedback(Block):
    """Sampled `u = -K z` — LQR or pole-placement gains."""

    inputs = ("z",)
    outputs = ("u",)
    discrete = True
    feedthrough = False

    def __init__(self, K: ArrayLike, name: str | None = None) -> None:
        super().__init__(name)
        self.K = np.atleast_1d(np.asarray(K, dtype=float)).ravel()
        self._held = 0.0

    def reset(self) -> None:
        self._held = 0.0

    def update(self, t: float, u: Inputs) -> None:
        self._held = float(-self.K @ np.atleast_1d(u["z"]))

    def output(self, t: float, x: NDArray[np.float64], u: Inputs) -> dict[str, Any]:
        return {"u": self._held}
