# Design note — block-diagram simulation core

**Status:** accepted — phase 1 implemented, 32 unit tests green
**Scope:** new modules `fuzzy/sim.py`, `fuzzy/blocks.py`, `fuzzy/metrics.py`
**Motivation:** remove the plant/controller/integrator coupling that currently forces every
new experiment to copy a simulation loop.

This is the first `design-*.md` note in `docs/` (existing notes use the `research-*` prefix).
Convention proposed: `research-*` for theory, `design-*` for architecture decisions.

---

## 1. Problem

Every exercise script welds together plant, disturbance, controller, integrator, metrics, and
plotting. The consequences, measured in the current tree:

| Duplicated thing | Where |
| --- | --- |
| `_harmonic`, `_deriv` | `sdof_vibration.py:148-157`, `pid_comparison.py:105-112` (verbatim) |
| RK4 step loop | `sdof_vibration.py:172-204`, `pid_comparison.py:124-147` |
| Frequency sweep | `sdof_vibration.py:376-406`, `pid_comparison.py:259-293` |
| 3-panel time-domain figure | `sdof_vibration.py:327-359`, `pid_comparison.py:161-191` |
| "last 4 s" steady-state window | `sdof_vibration.py:362`, `:388`; `pid_comparison.py:193`, `:239`, `:272` (5×) |
| `n_steps = int(t_max/dt) + 1` | 3× |
| matplotlib palette / styling | 3× |

The 5× repetition of the metric window is why the transient-contamination bug
(`t_max=12 s` against a plant with `tau = 1/(zeta*omega_n) = 5 s`) had to be fixed in five
places to be fixed at all. That is the class of bug this note is designed to make
structurally impossible.

There is also a forward cost. Each of these is currently a new ~300-line script:

- LQR benchmark against the fuzzy controller
- Luenberger / Kalman observer, so the controller stops receiving free perfect velocity
- multi-DOF plant (already written as `M x'' + C x' + K x = -M 1 x_g'' + B u` in
  `research-solid-mech-dynamics.md`)
- ANFIS controller in the loop

All four are "same harness, different block".

## 2. Non-goals

Stated explicitly, because the natural failure mode here is building a Simulink clone
instead of doing fuzzy-logic research:

- **No GUI.** Deliverables are markdown + matplotlib. A canvas ships nothing. Text-as-model
  is also strictly better for research: git-diffable, reviewable, and loopable for parameter
  sweeps (which `.slx` is not).
- **No acausal / implicit equation modelling** (Modelica-style). Signal flow only.
- **No algebraic-loop solver.** Detect, raise a clear error, tell the user to insert a `ZOH`
  or `UnitDelay`. Every physical plant here has `D = 0`, so this never triggers in practice.
- **No variable-step solvers, no zero-crossing detection.** Fixed-step RK4 is already
  grid-converged for these plants (0.4 % between `dt = 5 ms` and `dt = 1.25 ms`).
- **No multi-rate sample-time propagation.** One control rate, one integration rate. See §4.
- **No code generation.**

**Block-library discipline:** no block is written unless a current or immediately-next
exercise needs it. No speculative blocks.

## 3. Core model

Two orthogonal properties instead of a deep class hierarchy.

```python
class Block:
    name: str
    inputs:  tuple[str, ...]   # port names
    outputs: tuple[str, ...]
    n_states: int = 0          # 0 => algebraic
    feedthrough: bool = True   # does output() depend on u? (False breaks loops)

    def output(self, t: float, x: NDArray, u: Mapping[str, Any]) -> dict[str, Any]: ...
    def derivative(self, t: float, x: NDArray, u: Mapping[str, Any]) -> NDArray: ...
```

`derivative` is defined only when `n_states > 0`. A `SISO` base class supplies the port
boilerplate for the common single-in/single-out case.

Connections are explicit, no operator overloading:

```python
d.connect((plant, "y"), (ctrl, "x"))
d.connect(plant, ctrl)              # shorthand when both are single-port
```

### 3.1 Blocks needed by phases 1–3

| Block | States | Feedthrough | Needed by |
| --- | --- | --- | --- |
| `StateSpacePlant(A, B, C, D, x0)` | n | `D != 0` | ex. 2, multi-DOF later |
| `Harmonic(amplitude, omega, phase)` | 0 | — (source) | ex. 2 |
| `Step`, `Constant` | 0 | — | ex. 1 setpoint work |
| `Gain(k)`, `Sum(ports, signs)` | 0 | yes | wiring |
| `Select(index)` | 0 | yes | splitting a plant state vector into scalars |
| `Saturation(lo, hi)` | 0 | yes | actuator limits |
| `FISBlock(fis, input_map, clip)` | 0 | yes | ex. 1, ex. 2 |
| `PIDBlock(kp, ki, kd, Tt, lo, hi)` | 1 | yes | comparison |
| `ZOH(inner, dt)` | — | no | hybrid controller |
| `LQRBlock(K)` | 0 | yes | phase 3 |
| `Observer(A, B, C, L)` | n | yes | phase 3 |

`FISBlock` wraps `MamdaniFIS` and owns the input clipping currently inlined at
`sdof_vibration.py:183-184`. It also owns the **input scaling gains** — which is where the
`u = -(k1*x + k2*v)` equivalence and the universe-rescaling result belong as a first-class,
tunable parameter rather than a hardcoded universe bound.

## 4. Execution semantics

**Key property: a diagram of continuous blocks is itself one ODE.** All continuous states
concatenate into a single vector `z`, and the diagram exposes one `derivative(t, z)`:

1. unpack `z` into per-block state slices
2. evaluate the algebraic network in topological order to resolve every block's inputs
3. ask each stateful block for `xdot`
4. concatenate

A single RK4 then integrates the whole diagram. The existing RK4 works unchanged; this is
the same structure Simulink and Drake use internally.

**Hybrid loop.** The controller is zero-order-held, matching a real discrete-time
implementation:

```
for k in control_steps:
    u_k = evaluate discrete section at t_k    # controller sees current plant state
    hold u_k
    RK4 the continuous ODE over [t_k, t_k + dt_control] with u frozen   # n_substeps inside
    log every block output
```

This **separates control rate from integration step**, which the current code conflates into
a single `dt` (`sdof_vibration.py:172`). `n_substeps > 1` lets integration be finer than
sampling without changing controller behaviour — needed to verify grid convergence honestly.

**Algebraic loops.** Topological sort over feedthrough edges only. A cycle raises
`AlgebraicLoopError` naming the blocks involved and suggesting a `ZOH`/`UnitDelay`
breakpoint.

## 5. Logging and metrics

`simulate()` returns a `Log`: `t` plus every block output keyed `"<block>.<port>"`, as
dict-of-arrays. This replaces the ad-hoc per-script return dicts and makes plotting generic.

Metrics move to `fuzzy/metrics.py` — one definition, not five:

```python
def steady_state(log, key, window, tau=None) -> dict   # peak, rms, mean
```

**The transient guard.** `Diagram.slowest_tau()` returns `1 / min|Re(eig(A))|` over the
linearised continuous section. `steady_state()` warns when
`t_max - window < 4 * tau` — i.e. when the requested window is not actually steady state.
On the current exercise-2 setup (`t_max=12`, `window=4`, `tau=5`) this fires immediately,
which is exactly the intended behaviour: the bug becomes loud instead of silent.

## 6. Mermaid export (phase 3)

`Diagram.to_mermaid()` walks blocks and connections and emits a flowchart. ~40 lines.

`REPORT_comparison.md:132` already promises "one block diagram" that does not exist as a
figure. Generating it from the executable model means the published diagram can never drift
from the code that produced the numbers — an advantage over Simulink, where the diagram is
the model but cannot be diffed or regenerated.

## 7. Layout impact

Three new modules in `fuzzy/`, no new dependencies, no new top-level directory:

```
fuzzy/
  sim.py        # Diagram, simulate(), RK4, Log, AlgebraicLoopError
  blocks.py     # block classes
  metrics.py    # steady_state and friends
tests/unit/     # NEW — currently absent
```

Deferred to a follow-up note: `fuzzy/plotting.py` for the 3× duplicated matplotlib styling.
Real, but not on the critical path.

Also needed and currently missing: a `pyproject.toml` so `pip install -e .` replaces the
`sys.path.insert` + `# noqa: E402` prologue in every script.

## 8. Tests

`tests/unit/` does not exist today; this is where it starts. The charter requires a unit test
per new public function. Minimum set:

| Test | Asserts |
| --- | --- |
| `test_toposort` | known DAG orders correctly |
| `test_algebraic_loop_raises` | feedthrough cycle raises with block names |
| `test_rk4_exponential` | `x' = -x` matches `exp(-t)` to 1e-8 |
| `test_plant_free_decay` | SDOF free response envelope matches `exp(-zeta*omega_n*t)` |
| `test_closed_loop_eigenvalues` | plant + `Gain` feedback matches analytic poles |
| `test_zoh_holds` | output constant across a control interval |
| `test_partition_of_unity` | MF partitions sum to 1 (locks in a verified property) |
| `test_steady_state_warns_on_transient` | guard fires when `t_max - window < 4*tau` |
| `test_ex2_regression` | refactored exercise 2 reproduces current metrics |

## 9. Phasing

1. **Core + tests.** `sim.py`, `blocks.py`, `metrics.py`, `tests/unit/`, `pyproject.toml`.
   No exercise touched. Exit criterion: tests green.
2. **Refactor exercise 2 and the PID comparison onto it.** Exit criterion: metrics reproduce
   the current published numbers, *then* fix `t_max` once and regenerate figures/reports.
3. **`to_mermaid()`, `LQRBlock`, `Observer`.** Unblocks the state-space follow-ups and the
   missing block-diagram figures.
4. **Exercise 1** refactor, together with its V/s-vs-rpm/s unit fix and the equilibrium
   claims. Separate change — it has report corrections entangled with it.

## 10. Validation

**Result (phase 1): behaviour-preserving to machine precision.** Exercise 2 was rebuilt on
the core and compared against `sdof_vibration.simulate()` sample by sample:

```
max |x_new - x_old| = 1.8e-13        max |u_new - u_old| = 3.1e-12
```

So the diagram core, its scheduler, and its ZOH semantics reproduce the hand-rolled loop
exactly. Windowed metrics agree: `peak |x|` open `0.2270`, fuzzy `0.0742`.

### 10.1 A metric inconsistency this surfaced

`peak |u|` came out `0.7427` against a published `0.7443`. Cause: `sdof_vibration.py:372`
computes `u_peak` over the **whole run** with no `last4` mask, while `:363-366` apply it to
every other entry in the same table. So the "Steady-state metrics (last 4 s)" tables in
`REPORT.md` §9.1 and `REPORT_comparison.md` §3.2 mix a whole-run maximum into a windowed
row. The steady-state value is `0.7427`.

Not a physics error, but it is a mislabelled number in a published results table, and it
must be resolved in phase 2 — the `steady_state()` helper makes the windowed reading the
only convenient one.

### 10.2 Scaling gains are now a parameter

`FISBlock.gain` reproduces the universe-rescaling study as a sweep rather than a scratch
script, on a properly settled horizon (`t_max=40`):

| gain | peak \|x\| (m) | rms (m) | peak \|u\| (N) |
| ---: | ---: | ---: | ---: |
| 1 | 0.0734 | 0.0521 | 0.737 |
| 2 | 0.0430 | 0.0305 | 0.839 |
| 4 | 0.0236 | 0.0166 | 0.906 |
| 10 | 0.0102 | 0.0071 | 0.968 |

(PID reference: peak `0.0093`, `peak |u| = 0.967`.)

All 12 committed figures currently regenerate bit-identically, so any diff during the
phase-2 refactor is a real regression signal, not noise.

## 11. Risk

The honest risk is scope creep: a simulation framework is more fun to build than ANFIS, and
`rules.py` / `anfis.py` are still empty docstrings. Mitigations: the non-goals in §2, the
no-speculative-blocks rule, and the phase-1 exit criterion being *tests green*, not *feature
complete*.
