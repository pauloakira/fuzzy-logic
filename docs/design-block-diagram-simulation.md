# Design note — block-diagram simulation core

**Status:** accepted — phases 1-3 implemented, 50 unit tests green
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

## 2. Goals and non-goals

**A graphical block-diagram editor is a project goal** (decided 2026-07-29). An earlier draft
of this note listed "no GUI" as a non-goal on the reasoning that the deliverables are
markdown and matplotlib; that was overruled, and §11 records what the UI requires from the
core. The engineering consequence is concrete and worth stating up front: **a UI needs a
serializable declarative model**, which the imperative `Diagram.connect(...)` API does not
by itself provide.

The one property the UI must not cost us is text-as-model: git-diffable, reviewable, and
loopable for parameter sweeps. Simulink's `.slx` fails all three, and a frequency sweep is a
`for` loop here and a chore there. So the canvas must read and write a plain-text spec that
remains the source of truth — the diagram file is authored *either* way, never only by mouse.

Still out of scope:

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

Three orthogonal properties instead of a deep class hierarchy.

```python
class Block:
    name: str
    inputs:  tuple[str, ...]   # port names
    outputs: tuple[str, ...]
    n_states: int = 0          # 0 => algebraic
    feedthrough: bool = True   # does output() depend on u? (False breaks loops)
    discrete: bool = False     # sampled at the control rate, output held between

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

### 3.1 Blocks (as implemented)

| Block | States | Feedthrough | Needed by |
| --- | --- | --- | --- |
| `StateSpacePlant(A, B, C, D, x0)` | n | `D != 0` | ex. 2, multi-DOF later |
| `Harmonic(amplitude, omega, phase)` | 0 | — (source) | ex. 2 |
| `Step`, `Constant` | 0 | — | ex. 1 setpoint work |
| `Gain(k)`, `Sum(ports, signs)` | 0 | yes | wiring |
| `Select(index)` | 0 | yes | splitting a plant state vector into scalars |
| `Saturation(lo, hi)` | 0 | yes | actuator limits |
| `FISBlock(fis, gain, clip)` | 0 | sampled | ex. 1, ex. 2 |
| `PIDBlock(kp, ki, kd, lo, hi, Tt)` | 0 | sampled | comparison |
| `StateFeedback(K)` | 0 | sampled | phase 5 (LQR) |
| `Observer(A, B, C, L)` | n | yes | phase 5 — not yet written |

Sampling turned out to be a *property* of a controller block (`discrete = True`), not a
separate `ZOH` wrapper as first sketched: the block holds its own value and the outer loop
calls `update()` once per control step. `PIDBlock` therefore carries its integrator as
internal discrete state rather than as a diagram state, which is what makes it reproduce
`pid_comparison.py` exactly. `sdof_plant(m, c, k)` is a thin `StateSpacePlant` factory.

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

## 6. Mermaid export

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

The editor goal (§11) inserts a step: the declarative spec now comes **before** the exercise
port, so the exercises are built from the same representation the canvas will load rather
than being ported twice.

1. ~~**Core + tests.**~~ **Done** — `sim.py`, `blocks.py`, `metrics.py`, `tests/unit/`,
   `pyproject.toml`. 32 tests green, no exercise touched. See §10.
2. **Declarative spec + registry.** `fuzzy/spec.py`: block registry, per-block parameter
   schema, `Diagram.to_spec()` / `Diagram.from_spec()`, JSON round-trip, layout metadata
   passthrough. Stack-independent, so it is safe to build before the UI stack is chosen.
3. ~~**Port exercise 2 and the PID comparison.**~~ **Done** — both scripts now build a
   diagram instead of a bespoke RK4 loop, `diagram.json` is emitted as an editor fixture, and
   the horizon and `u_peak` mask are fixed. See §10.3.
4. **Declarative membership functions and rule bases.** The largest remaining piece and a
   hard prerequisite for editing fuzzy controllers in the UI — see §11.3.
5. **`LQRBlock`, `Observer`, Mermaid figures in the reports.** Unblocks the state-space
   follow-ups.
6. **Exercise 1** refactor, together with its V/s-vs-rpm/s unit fix and the equilibrium
   claims. Separate change — it has report corrections entangled with it.
7. **The editor itself.** Stack decision deferred to §11.6.

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

All 12 committed figures regenerated bit-identically before the port, so any diff was a
real regression signal rather than noise.

### 10.3 Phase 3 outcome

Both scripts reproduced every published number at the *old* horizon before any fix landed —
open `0.2270`, fuzzy `0.0742`, PID `0.0093`, PID `peak |u| 0.967` — confirming the port was
behaviour-preserving. The horizon and mask fixes then went in, giving:

| Metric | Open loop | Fuzzy | PID |
| --- | ---: | ---: | ---: |
| peak \|x\| (m) | 0.2499 | 0.0734 | 0.0093 |
| rms x (m) | 0.1782 | 0.0521 | 0.0066 |
| peak \|u\| (N) | — | 0.737 | 0.965 |
| reduction (peak) | — | 70.6 % | 96.3 % |

The open-loop peak now matches the analytic `F0/(c*omega_n) = 0.2500 m` to four decimals,
which is the check the old horizon could not pass.

Two smaller findings fell out of the port:

- The old RMS figures (`0.1532`, `0.0526`) were off in the fourth decimal because the
  hand-rolled loop **accumulated** `t[i+1] = t[i] + dt`, drifting `4.8e-13` by t=12 s — just
  enough to push the `t >= 8.0` window boundary across a sample and include 800 points
  instead of 801. `simulate()` recomputes `t = t0 + k*dt`, so the window is exact.
- The fuzzy `gain` sweep is now a published deliverable (`figures/gain_sweep.png`), and it
  reverses the comparison report's central conclusion. At gain 10 the same 25-rule controller
  reaches `0.0102 m` against PID's `0.0093 m` at equal effort, because both end up placing
  nearly the same closed-loop poles (fuzzy `zeta = 0.327` vs PID `0.456`, from a least-squares
  fit of `u = -(k1 x + k2 v)` to the control surface). `REPORT_comparison.md` §3.4 and §4.1
  were rewritten; the claim that the fuzzy limitation was "structural, not implementational"
  was wrong.

## 11. What the graphical editor requires from the core

The canvas is phase 7, but it constrains phases 2–4, so the requirements are recorded now.
Everything below is stack-independent — which is the argument for building the spec layer
before picking a UI technology.

### 11.1 A serializable spec as the source of truth

The imperative API builds a `Diagram` from live Python objects holding closures. That cannot
round-trip through a file. The editor needs a flat, declarative document:

```json
{
  "version": 1,
  "blocks": [
    {"type": "sdof_plant", "name": "plant",
     "params": {"m": 1.0, "c": 0.4, "k": 100.0}, "layout": {"x": 320, "y": 140}},
    {"type": "Harmonic", "name": "force", "params": {"amplitude": 1.0, "omega": 10.0}}
  ],
  "connections": [
    {"from": ["force", "y"], "to": ["total", "ext"]}
  ]
}
```

`Diagram.from_spec(spec)` and `Diagram.to_spec()` must round-trip losslessly. Scripts keep
using the imperative API where it is more pleasant; both produce the same object.

### 11.2 A block registry with parameter schemas

`"sdof_plant"` must resolve to a factory, and each block must describe its parameters (name,
type, default, units, bounds) so the editor renders a property panel generically instead of
hardcoding a form per block. Adding a block should make it appear in the palette for free.

### 11.3 Declarative membership functions and rule bases

This is the real work, and it is the reason phase 4 exists. Today a term is an opaque
closure built inline in each exercise:

```python
"NG": lambda x: left_shoulder(x, -0.3, -0.15)
```

A closure cannot be serialised, inspected, or edited. Terms must become data —
`{"type": "left_shoulder", "params": [-0.3, -0.15]}` — with `MamdaniFIS` constructible from
that description. Same for the rule base: the 5×5 table is currently built by a Python loop
over `TERM_ORDER`, and the editor needs it as an addressable grid.

This also pays off outside the UI: it is what makes `fuzzy/rules.py` (still an empty
docstring) a real module, and it removes the per-exercise MF boilerplate the audit flagged.

### 11.4 Machine-readable validation

`WiringError` and `AlgebraicLoopError` currently carry human-readable strings. The canvas
needs to highlight the offending node, so they must also carry structured references to the
blocks and ports involved.

### 11.5 Layout metadata

Node positions belong in the spec but must be ignored by the simulator and preserved across
round-trips. `to_mermaid()` (§6) stays useful as the headless renderer for reports.

### 11.6 Stack — deliberately deferred

To be decided after phase 2, when the spec exists and the choice is reversible:

- **Local web app** (FastAPI/Flask + a JS flow canvas). Best canvas ergonomics; adds a
  JS toolchain.
- **Native** (PySide/PyQt). Pure Python, no toolchain; more code for a good canvas.
- **Notebook widget** (anywidget/ipywidgets). Cheapest to reach, fits the exploratory
  workflow; weakest as a standalone tool.

Constraint on all three: the simulator must remain runnable headless, with no UI import on
the `simulate()` path.

## 12. Risk

The honest risk is scope creep: a simulation framework is more fun to build than ANFIS, and
`rules.py` / `anfis.py` are still empty docstrings. Mitigations: the non-goals in §2, the
no-speculative-blocks rule, and the phase-1 exit criterion being *tests green*, not *feature
complete*.
