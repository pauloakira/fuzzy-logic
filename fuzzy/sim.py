"""Block-diagram simulation core.

The load-bearing idea: **a diagram of continuous blocks is itself one ODE.** All
continuous states concatenate into a single vector `z`, and the diagram exposes a
single `derivative(t, z)`, so one fixed-step RK4 integrates the whole system.

Sampled (`discrete`) blocks model a zero-order-held digital controller: they are
updated once per control step and their outputs are frozen while the continuous
part is integrated across the interval.

Scope limits are deliberate — see `docs/design-block-diagram-simulation.md`:
no acausal modelling, no algebraic-loop solver, no variable-step integration, no
multi-rate sample-time propagation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

import numpy as np
from numpy.typing import NDArray

from fuzzy.blocks import Block

PortSpec = "Block | tuple[Block, str]"


class AlgebraicLoopError(RuntimeError):
    """A cycle of direct-feedthrough blocks. Insert a sampled block to break it."""


class WiringError(ValueError):
    """The diagram is not a valid, fully connected system."""


# ----- Log -------------------------------------------------------------------


@dataclass
class Log:
    """Simulation output: `t` plus every block output keyed `"<block>.<port>"`."""

    t: NDArray[np.float64]
    signals: dict[str, NDArray[np.float64]]

    def __getitem__(self, key: str) -> NDArray[np.float64]:
        if key == "t":
            return self.t
        try:
            return self.signals[key]
        except KeyError:
            raise KeyError(
                f"no signal {key!r}; available: {sorted(self.signals)}"
            ) from None

    def col(self, key: str, index: int) -> NDArray[np.float64]:
        """One component of a vector-valued signal, e.g. `col("plant.y", 0)`."""
        return np.asarray(self[key])[:, index]

    def keys(self) -> list[str]:
        return ["t", *sorted(self.signals)]


# ----- Diagram ---------------------------------------------------------------


class Diagram:
    """A set of blocks plus the wiring between their ports."""

    def __init__(self, name: str = "diagram") -> None:
        self.name = name
        self._blocks: list[Block] = []
        self._conns: dict[tuple[Block, str], tuple[Block, str]] = {}
        self._order: list[Block] | None = None

    # -- construction --

    def add(self, *blocks: Block) -> Block | tuple[Block, ...]:
        for b in blocks:
            if any(b.name == other.name for other in self._blocks):
                raise WiringError(f"duplicate block name {b.name!r}")
            self._blocks.append(b)
        self._order = None
        return blocks[0] if len(blocks) == 1 else blocks

    def connect(self, src: Any, dst: Any) -> None:
        """Wire an output port to an input port.

        Accepts `(block, "port")` pairs, or bare blocks when the block has
        exactly one port on the relevant side.
        """
        sb, sp = self._resolve(src, "outputs")
        db, dp = self._resolve(dst, "inputs")
        for b in (sb, db):
            if b not in self._blocks:
                self.add(b)
        if (db, dp) in self._conns:
            raise WiringError(f"input {db.name}.{dp} is already connected")
        self._conns[(db, dp)] = (sb, sp)
        self._order = None

    def _resolve(self, spec: Any, side: str) -> tuple[Block, str]:
        if isinstance(spec, Block):
            ports: tuple[str, ...] = getattr(spec, side)
            if len(ports) != 1:
                raise WiringError(
                    f"{spec.name!r} has {len(ports)} {side}; name one explicitly"
                )
            return spec, ports[0]
        block, port = spec
        if port not in getattr(block, side):
            raise WiringError(f"{block.name!r} has no {side[:-1]} port {port!r}")
        return block, port

    # -- validation and scheduling --

    def _finalize(self) -> list[Block]:
        if self._order is not None:
            return self._order

        for b in self._blocks:
            for p in b.inputs:
                if (b, p) not in self._conns:
                    raise WiringError(f"input {b.name}.{p} is not connected")

        # A source->dest edge constrains scheduling only when the destination
        # actually reads its inputs to produce its output.
        preds: dict[Block, set[Block]] = {b: set() for b in self._blocks}
        for (db, _), (sb, _) in self._conns.items():
            if db.feedthrough:
                preds[db].add(sb)

        order: list[Block] = []
        remaining = dict(preds)
        while remaining:
            ready = [b for b, ps in remaining.items() if not (ps & remaining.keys())]
            if not ready:
                raise AlgebraicLoopError(
                    "direct-feedthrough cycle among: "
                    + ", ".join(sorted(b.name for b in remaining))
                    + " — insert a sampled block (FISBlock/PIDBlock) to break it"
                )
            ready.sort(key=lambda b: self._blocks.index(b))
            order.extend(ready)
            for b in ready:
                del remaining[b]

        self._check_discrete_chain()
        self._order = order
        return order

    def _check_discrete_chain(self) -> None:
        """Phase-1 limit: a sampled block may not feed another sampled block."""
        for d in (b for b in self._blocks if b.discrete):
            stack = [self._conns[(d, p)][0] for p in d.inputs]
            seen: set[Block] = set()
            while stack:
                s = stack.pop()
                if s in seen:
                    continue
                seen.add(s)
                if s.discrete:
                    raise WiringError(
                        f"sampled block {d.name!r} depends on sampled block "
                        f"{s.name!r}; multi-rate chains are out of scope"
                    )
                if s.feedthrough:
                    stack.extend(self._conns[(s, p)][0] for p in s.inputs)

    @property
    def blocks(self) -> tuple[Block, ...]:
        return tuple(self._blocks)

    # -- state --

    def _layout(self) -> list[tuple[Block, slice]]:
        out, i = [], 0
        for b in self._blocks:
            if b.n_states:
                out.append((b, slice(i, i + b.n_states)))
                i += b.n_states
        return out

    @property
    def n_states(self) -> int:
        return sum(b.n_states for b in self._blocks)

    def initial_state(self) -> NDArray[np.float64]:
        parts = [b.initial_state() for b in self._blocks if b.n_states]
        return np.concatenate(parts) if parts else np.zeros(0)

    def reset(self) -> None:
        for b in self._blocks:
            b.reset()

    # -- evaluation --

    def _gather(
        self, b: Block, out: Mapping[tuple[Block, str], Any]
    ) -> dict[str, Any]:
        u = {}
        for p in b.inputs:
            src = self._conns[(b, p)]
            if src in out:
                u[p] = out[src]
        return u

    def evaluate(
        self, t: float, z: NDArray[np.float64]
    ) -> tuple[dict[tuple[Block, str], Any], dict[Block, dict[str, Any]]]:
        """Resolve every block output at `(t, z)`, then every block's inputs."""
        order = self._finalize()
        spans = dict(self._layout())
        out: dict[tuple[Block, str], Any] = {}
        for b in order:
            x = z[spans[b]] if b in spans else np.zeros(0)
            for port, value in b.output(t, x, self._gather(b, out)).items():
                out[(b, port)] = value
        ins = {b: self._gather(b, out) for b in self._blocks}
        return out, ins

    def derivative(
        self, t: float, z: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """The whole diagram as a single ODE right-hand side."""
        _, ins = self.evaluate(t, z)
        dz = np.zeros_like(z)
        for b, span in self._layout():
            dz[span] = np.atleast_1d(b.derivative(t, z[span], ins[b]))
        return dz

    def sample(self, t: float, z: NDArray[np.float64]) -> None:
        """Update every sampled block from the current continuous state."""
        sampled = [b for b in self._blocks if b.discrete]
        if not sampled:
            return
        _, ins = self.evaluate(t, z)
        for b in sampled:
            b.update(t, ins[b])

    # -- analysis --

    def slowest_tau(self, tol: float = 1e-9) -> float | None:
        """Slowest open-loop time constant `1 / min|Re(eig)|` over LTI blocks.

        Used by `fuzzy.metrics.steady_state` to warn when a "steady-state"
        window is still contaminated by transient. Returns `None` when no block
        exposes `eigenvalues()`.
        """
        rates: list[float] = []
        for b in self._blocks:
            eig = getattr(b, "eigenvalues", None)
            if eig is None:
                continue
            rates.extend(abs(float(np.real(v))) for v in eig())
        decaying = [r for r in rates if r > tol]
        return 1.0 / min(decaying) if decaying else None

    def to_mermaid(self) -> str:
        """Mermaid flowchart of the wiring (phase 3 uses this for the reports)."""
        lines = ["flowchart LR"]
        for b in self._blocks:
            shape = "[/{}\\]" if not b.inputs else ("([{}])" if b.discrete else "[{}]")
            lines.append(f"    {b.name}{shape.format(b.name)}")
        for (db, dp), (sb, sp) in self._conns.items():
            label = f"|{sp}→{dp}|" if (len(sb.outputs) > 1 or len(db.inputs) > 1) else ""
            lines.append(f"    {sb.name} -->{label} {db.name}")
        return "\n".join(lines)


# ----- Integration -----------------------------------------------------------

Deriv = Callable[[float, NDArray[np.float64]], NDArray[np.float64]]


def rk4_step(
    f: Deriv, t: float, z: NDArray[np.float64], h: float
) -> NDArray[np.float64]:
    """One classical fourth-order Runge-Kutta step."""
    k1 = f(t, z)
    k2 = f(t + h / 2, z + h / 2 * k1)
    k3 = f(t + h / 2, z + h / 2 * k2)
    k4 = f(t + h, z + h * k3)
    return z + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


def simulate(
    diagram: Diagram,
    *,
    t_max: float,
    dt_control: float,
    n_substeps: int = 1,
    t0: float = 0.0,
) -> Log:
    """Run `diagram` over `[t0, t_max]`, sampling controllers every `dt_control`.

    `n_substeps` sets how many RK4 steps happen inside each control interval, so
    the integration step and the control rate are independent — that separation
    is what makes a grid-convergence check meaningful.
    """
    if dt_control <= 0 or n_substeps < 1:
        raise ValueError("`dt_control` must be positive and `n_substeps` >= 1")

    diagram.reset()
    n_steps = int(round((t_max - t0) / dt_control)) + 1
    h = dt_control / n_substeps

    z = diagram.initial_state()
    times = np.empty(n_steps)
    frames: list[dict[tuple[Block, str], Any]] = []

    for k in range(n_steps):
        t = t0 + k * dt_control  # recomputed, not accumulated, to avoid drift
        diagram.sample(t, z)
        out, _ = diagram.evaluate(t, z)
        times[k] = t
        frames.append(out)
        if k == n_steps - 1:
            break
        t_sub = t
        for _ in range(n_substeps):
            z = rk4_step(diagram.derivative, t_sub, z, h)
            t_sub += h

    signals = {
        f"{b.name}.{p}": np.array([np.asarray(f[(b, p)]) for f in frames])
        for (b, p) in frames[0]
    }
    return Log(t=times, signals=signals)


def sweep(
    diagram: Diagram,
    setter: Callable[[float], None],
    values: Iterable[float],
    **kwargs: Any,
) -> list[Log]:
    """Run the same diagram once per parameter value (e.g. a frequency sweep)."""
    logs = []
    for v in values:
        setter(v)
        logs.append(simulate(diagram, **kwargs))
    return logs
