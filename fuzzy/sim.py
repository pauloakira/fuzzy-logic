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

import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from fuzzy.blocks import Block

PortSpec = "Block | tuple[Block, str]"


class AlgebraicLoopError(RuntimeError):
    """A cycle of direct-feedthrough blocks. Insert a sampled block to break it.

    `.blocks` names every block in the cycle, so an editor can highlight the whole
    loop rather than making the user read it out of the message.
    """

    def __init__(self, message: str, blocks: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.blocks = list(blocks)


class WiringError(ValueError):
    """The diagram is not a valid, fully connected system.

    `.block`, `.port`, and `.related` carry structured references to what is
    wrong, so a canvas can highlight the offending node or wire instead of only
    printing a sentence. Any of them may be `None` when not applicable.
    """

    def __init__(
        self,
        message: str,
        block: str | None = None,
        port: str | None = None,
        related: str | None = None,
    ) -> None:
        super().__init__(message)
        self.block = block
        self.port = port
        self.related = related


# ----- Log -------------------------------------------------------------------


@dataclass
class Log:
    """Simulation output: `t` plus every block output keyed `"<block>.<port>"`.

    `z_final` is the diagram's state vector at the last sample. It is not a
    signal — a block's *state* and its *output* differ whenever `C` is not the
    identity, and `MotorPlant` clips its output — so it cannot be recovered from
    `signals`. It is here because the settled state is the operating point worth
    linearizing about, and it is free at the end of a run.
    """

    t: NDArray[np.float64]
    signals: dict[str, NDArray[np.float64]]
    z_final: NDArray[np.float64] = field(default_factory=lambda: np.zeros(0))

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
        self.layout: dict[str, dict[str, float]] = {}
        """Canvas positions per block name. Ignored by the simulator; preserved
        across spec round-trips so a graphical editor can own it."""
        self._blocks: list[Block] = []
        self._conns: dict[tuple[Block, str], tuple[Block, str]] = {}
        self._order: list[Block] | None = None

    # -- construction --

    def add(self, *blocks: Block) -> Block | tuple[Block, ...]:
        for b in blocks:
            if any(b.name == other.name for other in self._blocks):
                raise WiringError(f"duplicate block name {b.name!r}", block=b.name)
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
            raise WiringError(
                f"input {db.name}.{dp} is already connected",
                block=db.name,
                port=dp,
                related=self._conns[(db, dp)][0].name,
            )
        self._conns[(db, dp)] = (sb, sp)
        self._order = None

    def _resolve(self, spec: Any, side: str) -> tuple[Block, str]:
        if isinstance(spec, Block):
            ports: tuple[str, ...] = getattr(spec, side)
            if len(ports) != 1:
                raise WiringError(
                    f"{spec.name!r} has {len(ports)} {side}; name one explicitly",
                    block=spec.name,
                )
            return spec, ports[0]
        block, port = spec
        if port not in getattr(block, side):
            raise WiringError(
                f"{block.name!r} has no {side[:-1]} port {port!r}",
                block=block.name,
                port=port,
            )
        return block, port

    # -- validation and scheduling --

    def _finalize(self) -> list[Block]:
        if self._order is not None:
            return self._order

        for b in self._blocks:
            for p in b.inputs:
                if (b, p) not in self._conns:
                    raise WiringError(
                        f"input {b.name}.{p} is not connected", block=b.name, port=p
                    )

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
                cycle = sorted(b.name for b in remaining)
                raise AlgebraicLoopError(
                    "direct-feedthrough cycle among: "
                    + ", ".join(cycle)
                    + " — insert a sampled block (FISBlock/PIDBlock) to break it",
                    blocks=cycle,
                )
            ready.sort(key=lambda b: self._blocks.index(b))
            order.extend(ready)
            for b in ready:
                del remaining[b]

        self._check_discrete_chain()
        self._order = order
        return order

    def _check_discrete_chain(self) -> None:
        """A sampled block may not read another sampled block's *stale* output.

        `sample()` updates every sampled block from one evaluation of the
        continuous network, so it cannot order two sampled blocks against each
        other — if one fed another algebraically, the second would silently read
        the first's previous value.

        Tracing stops at any block carrying continuous state. Whatever such a
        block emits comes either from its integrated state (current) or from an
        input held constant across the interval, so no staleness crosses it.
        That is ordinary zero-order-hold structure, not a hazard: without this
        stop, a plant with direct feedthrough (`D != 0`) inside a sampled loop
        is rejected with a misleading multi-rate error.
        """
        for d in (b for b in self._blocks if b.discrete):
            stack = [self._conns[(d, p)][0] for p in d.inputs]
            seen: set[Block] = set()
            while stack:
                s = stack.pop()
                if s in seen or s.n_states:
                    continue
                seen.add(s)
                if s.discrete:
                    raise WiringError(
                        f"sampled block {d.name!r} depends on sampled block "
                        f"{s.name!r} through algebraic blocks only, so it would "
                        f"read a stale value; multi-rate chains are out of scope",
                        block=d.name,
                        related=s.name,
                    )
                if s.feedthrough:
                    stack.extend(self._conns[(s, p)][0] for p in s.inputs)

    @property
    def blocks(self) -> tuple[Block, ...]:
        return tuple(self._blocks)

    def block(self, name: str) -> Block:
        for b in self._blocks:
            if b.name == name:
                return b
        raise KeyError(f"no block named {name!r}")

    def connections(self) -> list[tuple[tuple[str, str], tuple[str, str]]]:
        """Wiring as `((src_block, src_port), (dst_block, dst_port))` name pairs."""
        return [
            ((sb.name, sp), (db.name, dp)) for (db, dp), (sb, sp) in self._conns.items()
        ]

    # -- state --

    def _layout(self) -> list[tuple[Block, slice]]:
        out, i = [], 0
        for b in self._blocks:
            if b.n_states:
                out.append((b, slice(i, i + b.n_states)))
                i += b.n_states
        return out

    def state_slices(self) -> dict[str, slice]:
        """Where each stateful block's states sit in the diagram's vector `z`.

        Public because a caller holding a `Log.z_final` has no other way to say
        which numbers belong to which block, and that is what an operating point
        for linearization is made of.
        """
        return {b.name: span for b, span in self._layout()}

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

    def _gather(self, b: Block, out: Mapping[tuple[Block, str], Any]) -> dict[str, Any]:
        u = {}
        for p in b.inputs:
            src = self._conns[(b, p)]
            if src in out:
                u[p] = out[src]
        return u

    def evaluate(
        self,
        t: float,
        z: NDArray[np.float64],
        inject: Mapping[str, Any] | None = None,
    ) -> tuple[dict[tuple[Block, str], Any], dict[Block, dict[str, Any]]]:
        """Resolve every block output at `(t, z)`, then every block's inputs.

        `inject` adds a perturbation to named signals (`"block.port"`) as they
        are produced, so everything downstream sees the perturbed value. A closed
        diagram has no free input ports — every one is wired — so this is the
        only way to ask what happens if a signal is nudged, which is exactly what
        `B` and `D` of a whole-diagram linearization are made of. It is the same
        idea as a Simulink linear-analysis input point.
        """
        order = self._finalize()
        spans = dict(self._layout())
        out: dict[tuple[Block, str], Any] = {}
        for b in order:
            x = z[spans[b]] if b in spans else np.zeros(0)
            for port, value in b.output(t, x, self._gather(b, out)).items():
                if inject:
                    delta = inject.get(f"{b.name}.{port}")
                    if delta is not None:
                        value = np.asarray(value, dtype=float) + delta
                out[(b, port)] = value
        ins = {b: self._gather(b, out) for b in self._blocks}
        return out, ins

    def derivative(
        self,
        t: float,
        z: NDArray[np.float64],
        inject: Mapping[str, Any] | None = None,
    ) -> NDArray[np.float64]:
        """The whole diagram as a single ODE right-hand side."""
        _, ins = self.evaluate(t, z, inject)
        dz = np.zeros_like(z)
        for b, span in self._layout():
            dz[span] = np.atleast_1d(b.derivative(t, z[span], ins[b]))
        return dz

    def signal_names(self) -> list[str]:
        """Every `"block.port"` output signal the diagram produces."""
        return [f"{b.name}.{p}" for b in self._blocks for p in b.outputs]

    def source_signals(self) -> list[str]:
        """Outputs of blocks with no inputs — the diagram's exogenous signals.

        These are the natural inputs of a closed loop: a disturbance or a
        reference enters here and nowhere else.
        """
        return [
            f"{b.name}.{p}"
            for b in self._blocks if not b.inputs
            for p in b.outputs
        ]

    def sample(
        self,
        t: float,
        z: NDArray[np.float64],
        inject: Mapping[str, Any] | None = None,
    ) -> None:
        """Update every sampled block from the current continuous state."""
        sampled = [b for b in self._blocks if b.discrete]
        if not sampled:
            return
        _, ins = self.evaluate(t, z, inject)
        for b in sampled:
            b.update(t, ins[b])

    # -- analysis --

    def fastest_mode(self) -> float | None:
        """Largest `|eigenvalue|` over LTI blocks — what bounds the step size."""
        mags: list[float] = []
        for b in self._blocks:
            eig = getattr(b, "eigenvalues", None)
            if eig is None:
                continue
            mags.extend(abs(complex(v)) for v in eig())
        return max(mags) if mags else None

    def stability_limit(self) -> float | None:
        """Largest integration step classical RK4 stays stable at, or None.

        RK4's stability region reaches `|lambda h| = 2sqrt(2) ~ 2.83` along the
        imaginary axis, which is the binding case for a lightly damped
        oscillator. Beyond it the solution grows without bound and overflows to
        `inf` silently, so `simulate()` warns rather than letting a plausible
        looking run be garbage.
        """
        fastest = self.fastest_mode()
        return RK4_STABILITY_RADIUS / fastest if fastest else None

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

    def to_mermaid(self, types: bool = True) -> str:
        """Mermaid flowchart of the wiring, for reports and documentation.

        Generated from the executable diagram, so a published figure cannot
        drift from the model that produced the numbers beside it. Sources are
        drawn as skewed boxes and sampled (zero-order-held) blocks as rounded
        ones, so the continuous/discrete split is visible at a glance.
        """
        lines = ["flowchart LR"]
        for b in self._blocks:
            label = f"{b.name}<br/>{type(b).__name__}" if types else b.name
            if not b.inputs:
                shape = f'[/"{label}"\\]'
            elif b.discrete:
                shape = f'(["{label}"])'
            else:
                shape = f'["{label}"]'
            lines.append(f"    {b.name}{shape}")
        for (db, dp), (sb, sp) in self._conns.items():
            named = len(sb.outputs) > 1 or len(db.inputs) > 1
            arrow = f"-->|{sp}→{dp}|" if named else "-->"
            lines.append(f"    {sb.name} {arrow} {db.name}")
        return "\n".join(lines)


# ----- Integration -----------------------------------------------------------

Deriv = Callable[[float, NDArray[np.float64]], NDArray[np.float64]]

RK4_STABILITY_RADIUS = 2.0 * np.sqrt(2.0)
"""Classical RK4 stays stable while `|lambda h|` is below this on the imaginary axis."""


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

    limit = diagram.stability_limit()
    if limit is not None and h > limit:
        warnings.warn(
            f"integration step {h:g} s exceeds the RK4 stability limit "
            f"{limit:.4g} s for this diagram's fastest mode "
            f"(|lambda| = {diagram.fastest_mode():.4g} rad/s). The run will grow "
            f"without bound. Reduce dt_control, or raise n_substeps to at least "
            f"{int(np.ceil(dt_control / limit))}.",
            UserWarning,
            stacklevel=2,
        )

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
    return Log(t=times, signals=signals, z_final=z)


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
