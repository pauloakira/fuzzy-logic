# Linearization

How `fuzzy/linearize.py` turns a nonlinear block into an `(A, B, C, D)` the Bode
plot and the pole–zero map can draw, and — the longer half of this note — where
that model is a lie. Written 2026-08-04.

## 1. What Ogata specifies

*Modern Control Engineering*, 5th ed., §2-7 "Linearization of Nonlinear
Mathematical Models". The procedure is a Taylor expansion about an operating
point with the higher-order terms dropped:

> the linearization procedure presented here is based on the expansion of a
> nonlinear function into a Taylor series about the operating point

For `x' = f(t, x, u)`, `y = g(t, x, u)` about `(x0, u0)` that gives

    dx' = A dx + B du,   dy = C dx + D du
    A = ∂f/∂x,  B = ∂f/∂u,  C = ∂g/∂x,  D = ∂g/∂u    all at (x0, u0)

Two conditions come with it, and both matter here:

1. **`f` must be differentiable at the operating point.** Ogata's derivation
   starts from a Taylor series, which a corner does not have.
2. **The result is only valid for small signals** about `(x0, u0)`. It says
   nothing about behaviour a finite distance away, and the charts drawn from it
   look exactly like charts of a genuinely linear plant.

## 2. Why the Jacobians are numerical

A block is Python, not a symbolic expression — `MotorPlant.derivative` calls
`np.clip`, `FISBlock` runs a Mamdani inference engine. There is nothing to
differentiate symbolically, so the Jacobians are central differences with step
`h = eps^(1/3) · max(|v|, 1)`, which is the standard optimum for a central
difference and relative for large coordinates without dividing by zero at small
ones.

The price is that a finite difference cannot tell a curve from a corner: at a
clip point it happily returns the *average* of the two one-sided slopes, a number
that describes the block in neither direction. §3 is about paying that price.

Sanity check on the method: an LTI block linearizes back to itself **bit for
bit** (`test_an_lti_block_linearizes_back_to_itself`), and `MotorPlant` away from
its limits reproduces the hand-computed `A = [[-1, k], [0, 0]]`, `B = [[0],
[1]]`, `C = I`, `D = 0`.

## 3. The two ways a limiter lies, and how each is caught

This is the part that produces confidently wrong charts, so both failure modes
are detected and reported in `Linearization.warnings`.

### 3.1 On the corner — a slope that exists in neither direction

At `u = 1` a `Saturation(-1, 1)` has slope 1 from the left and 0 from the right.
The central difference returns **0.5**, which is not the behaviour on either
side. Detected by computing the one-sided slopes from the same two evaluations
the central difference already needs, and reporting any coordinate where they
disagree by more than `CORNER_TOL = 1e-3` relative. A smooth function's one-sided
slopes agree to `O(h) ≈ 1e-5`; a corner makes them differ by `O(1)`, so the two
cases are separated by four orders of magnitude.

### 3.2 Inside saturation — a slope that is real, correct, and useless

Deep in a saturated region the block *is* differentiable, with slope exactly
zero, so §3.1 stays silent and the Jacobian is right. But a zero row of `[A B]`
means that state cannot be moved from the operating point at all, and its Bode
plot is a flat line that looks like a result. `MotorPlant` with its rate limit
saturated returns `A = [[0, 0], [0, 0]]`: a reader who trusts it concludes the
motor cannot turn.

Detected structurally rather than numerically — a state row zero in both `A` and
`B`, or an output row zero in both `C` and `D`. A pure source (no inputs, no
states) is exempt: a `Constant` is *supposed* to have a dead output, and warning
there would train the reader to ignore warnings.

### 3.3 `t = 0` is the worst place to linearize, so it is not the default

`MotorPlant`'s initial state is `(0 rpm, 0 V)` — both lower clamps at once. The
Jacobian there is a corner-average with `A[0,1]`, `B[1]` and every entry of `C`
at exactly half their true value, compounding to **1/8** on the speed channel
and **1/4** on the voltage channel: 18.06 dB and 12.04 dB of pure error on a
plot whose shape, phase, poles and zeros are all perfectly correct. Nothing
about the chart looks wrong.

So the editor linearizes about **the state at the end of the last run** by
default. It is free — `Log.z_final` falls out of the integration — and it is
almost always the meaningful operating point: the same motor after 800 s sits at
`(577.2 rpm, 57.7 V)`, well inside its envelope, where the model is exact and
the magnitudes come out at the correct 60 dB and 40 dB.

The picker above the charts offers the other two: each block's initial state
(the old behaviour, useful for seeing exactly this failure), and a state typed
by hand. `POST /api/analyze` takes the same thing as `operating_point`, and
`POST /api/simulate` returns one ready to forward.

**A related trap, found while wiring this up.** `frequency_grid` rounds out to
enclosing decades with `floor(log10(·))`. A numerical Jacobian returns a pole of
1 as `0.999999999995`, whose `log10` is `-2e-12`, and `floor` of that is `-1`
rather than `0` — so the exact model and the linearized one plotted the same
system over ranges a decade apart. Fixed by nudging before rounding.

## 4. Sampled blocks and the fuzzy controller's local gain

A `discrete` block's `output()` returns a held value; its dependence on `u` is
inside `update()`. So for those the map linearized is `u → update(); output()`,
driven on a `deepcopy` so the live block's held value survives the probing
(`test_probing_a_sampled_block_does_not_disturb_its_held_output`).

For a `FISBlock` this is more than plumbing. `D` is the local slope of the fuzzy
control surface — **the gain the fuzzy controller is applying right here**, in
the same units as a state-feedback `K`. At rest the exercise-2 controller
linearizes to `K ≈ [14.9, 1.49]`, and that changes with the operating point,
which is precisely what makes it not a linear controller. This is the natural
bridge to the LQR comparison in `docs/future-work.md` §2.1.

## 5. Equilibria

`equilibrium()` solves `f(x, u0) = 0` by Newton from a guess, with a
least-squares step rather than an inverse because `∂f/∂x` is routinely singular
here: `MotorPlant`'s voltage state is a pure integrator, so its equilibria form
the *line* `ω = kV` rather than a point. The minimum-norm step lands on the
closest point of that line to the guess — from `(0, 50)` it returns
`(4.95, 0.495)`, which is the nearest equilibrium, not the one holding `V` at 50.

Not every `u0` admits an equilibrium at all (drive the integrator off zero and
`V' = u ≠ 0` forever), so the residual is returned rather than raised on: a
caller that cares must check it.

## 6. Where this lives

- `fuzzy/linearize.py` — `linearize()`, `equilibrium()`, `Linearization`
- `POST /api/analyze` — linearizes any stateful non-`StateSpacePlant` block,
  marks the system `linearized: true`, and passes the warnings through
- `editor/static/app.js` `drawAnalysis()` — renders those warnings above the
  charts, because a linearized chart and a genuine one are indistinguishable
- Tests — `tests/unit/test_linearize.py` (Jacobians vs closed form, corner and
  degeneracy detection, equilibria), `tests/api/test_api.py`,
  `tests/e2e/test_analysis.py`

## 7. The whole diagram — the closed loop

`linearize_diagram()` linearizes the diagram itself. `A = ∂ż/∂z` over the
concatenated state vector, so its eigenvalues are the **closed-loop poles**: the
question of whether this controller stabilizes this plant, which no per-block
model can answer because it has the loop cut at every wire.

For `ex2_sdof_fuzzy` that is the headline number of the whole project:

| | ωn (rad/s) | ζ |
|---|---|---|
| plant alone | 9.998 | **0.020** |
| closed loop with the fuzzy controller | 10.72 | **0.088** |

Both are charted together, which is the comparison worth looking at.

### 7.1 Injection, because a closed diagram has no free inputs

Every input port of a wired diagram is connected, so there is nothing to
perturb for `B` and `D`. `Diagram.evaluate` therefore takes an `inject` mapping
that adds a delta to a named signal as it is produced, and everything downstream
sees it. `inputs` defaults to the diagram's *source* signals — where a
disturbance or reference actually enters. This is the same construct as a
Simulink linear-analysis input point, and it is what a loop-breaking open-loop
`L(s)` would be built on too.

### 7.2 Sampled blocks, and the approximation that buys the closed loop

A `discrete` block's `output()` returns a value held from the last control
instant. Left alone it has no dependence on the current state at all — so the
diagram would linearize **as though the loop were cut at the controller**, and
report the bare plant's poles with the controller apparently inert. That is a
silent, plausible, completely wrong answer.

So sampled blocks are re-sampled at every probe, on a deep copy. That models the
zero-order hold by its continuous equivalent and **ignores the sampling delay**.
It is the standard fast-sampling approximation and it is *optimistic*: a real ZOH
adds roughly `dt/2` of phase lag, so a loop that looks marginally stable here may
not be. Every diagram with a sampled block says so in its warnings.

Cross-checked rather than assumed: the closed-loop `A` equals
`plant.A + plant.B @ D` where `D` is the fuzzy controller's local gain taken
independently by `linearize()` — two different code paths agreeing to 1e-6
(`test_a_sampled_controller_actually_closes_the_loop`).

## 8. The open loop — `L(s)` and the margins

Ogata §2-3 defines the open-loop transfer function as the ratio of the fed-back
signal to the actuating error. `loop_transfer()` gets it by **cutting one wire**:
the block that produces the signal goes on producing it, while its consumers
receive an independent test value instead. That is a different operation from
§7.1's injection, and the distinction is the whole point —

| | what it does | what it is for |
|---|---|---|
| `inject` | **adds** a delta; producer and consumers both see it | disturbance response, `B` and `D` of the closed loop |
| `cut` | **replaces** what consumers see; the producer's own value stays readable | opening the loop, `L(s)` |

### 8.1 Sign convention

`(A, B, C, D)` comes back with `C` and `D` already negated, so

    L(s) = C (sI - A)^-1 B + D      and      1 + L(s) = 0

is the closed-loop characteristic equation — which puts the critical point at
`-1`, where Nyquist expects it. The raw measurement is `w_out/w_in`; the sign is
what a negative-feedback summing junction contributes in the block diagram.

`A` here is the **open-loop** state matrix. Its eigenvalues are the plant's own
poles, not the closed loop's — that is what cutting the loop means, and it is why
the s-plane chart does not redraw them in a second colour.

### 8.2 What it is checked against

Four independent ways, because a sign or a break point is easy to get wrong:

1. `L(jω)` matches the analytic `25/(ms² + cs + k)` of a hand-built loop to
   **1e-9**.
2. Closing unity negative feedback algebraically, `A - B C`, reproduces
   `linearize_diagram(...).A` **exactly** — two code paths that share nothing but
   the diagram.
3. `1 + L(s)` evaluates to zero at every closed-loop pole, which is the sign
   convention stated as a test rather than a comment.
4. Breaking at `total.y`, `controller.u` or `actuator.y` gives the **same**
   `L(jω)` to 1e-6. A single loop has one loop transfer; where you cut is
   bookkeeping.

### 8.3 Margins

`analysis.margins()` reads the two numbers `L(jω)` exists for (Ogata §7-6):
phase margin at the gain crossover (`|L| = 1`), gain margin at the phase
crossover (`∠L = -180°`), both interpolated in `log10(ω)` because the grid is
log-spaced.

Either is `None` when its crossover is not on the grid. The SDOF loop has no gain
margin at all — its phase approaches `-180°` without reaching it — and reporting
one by extrapolating past the data would be worse than saying so. Where a
crossover happens more than once, the smallest margin is returned, since that is
the one that binds.

The margins move with the operating point, which is the feature and not a flake:
the fuzzy loop reads **59.3°** about `z = 0` and **78.3°** about the state a 10 s
run settles at, because the controller's local gain is different there. `L(s)`
uses the same operating point as the closed loop, or the two would describe
different machines — on exercise 1 the diagram's initial state is the motor's
clamps, and `L(s)` taken there is a corner.

## 9. Nyquist and root locus

Both are complex-plane views of the same `L(s)`, drawn with equal scale on both
axes — the whole question in each is how close a curve comes to a point, and a
distance that does not read true answers it wrong.

**Nyquist** is `L(jω)` plotted against the `-1` point (Ogata §7-6), with the
mirror image for negative ω drawn dashed: that is what closes the contour and
makes an encirclement countable.

**Root locus** sweeps a scalar gain `k` and plots the closed-loop poles of
`1 + k L(s) = 0` (Ogata §6). `root_locus()` takes `L` as state space, so the
poles come from

    A_cl(k) = A - (k / (1 + k D)) B C

by an eigenvalue solve. No characteristic polynomial is ever formed, and none of
its conditioning problems arise. `k = 0` and `k = 1` are both forced into the
sweep and marked on the chart — the branch starts at the open-loop poles and
passes through the loop as actually built, and the tests assert both, since a
locus that misses the design point is drawing some other system.

Two details that are easy to get wrong:

- **Branch continuity.** `eigvals` returns roots in no order, so joining them
  index-by-index draws branches that teleport between poles. `_track` matches
  each root to its nearest predecessor. The ambiguous case — two branches meeting
  at a breakaway point — is one where either assignment draws the same picture.
- **Clipping.** The view is scaled to the 92nd percentile of `|point|`, because
  scaling to the maximum would crush everything that matters into one pixel when
  a locus runs off toward infinity. So part of the curve is outside the box *by
  construction*, and SVG does not clip on its own — without an explicit
  `clipPath` the overflow paints across whatever sits next to the chart.

## 10. Not done yet

- **A closed-loop operating point from the UI.** `/api/simulate` returns the
  diagram's settled `z` under `__diagram__` and `/api/analyze` accepts it, but
  the picker's "custom" mode only edits per-block states — those cannot be
  composed into the diagram's vector without knowing its layout, so the closed
  loop falls back to its own initial state rather than guess.
- **Trim.** `equilibrium()` solves for `x` at fixed `u`. Solving for both, subject
  to a target output, is the usual "trim" operation and is not implemented.
