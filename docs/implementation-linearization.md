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

### 3.3 The default operating point is often a corner

`MotorPlant`'s default initial state is `(0 rpm, 0 V)` — which is both lower
clamps at once. So exercise 1 opens with a linearization taken exactly on a
corner, and says so in three warnings. This is not a bug to paper over: it is
the honest answer, and the fix is to pick an operating point
(`POST /api/analyze` takes `operating_point`), not to quietly move it. With
`x = [500, 50]` the warnings disappear and the poles come out at `-1` and `0`.

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

## 7. Not done yet

- **Whole-diagram linearization.** Only individual blocks are linearized. The
  closed loop — plant plus fuzzy controller plus actuator, as one `(A, B, C, D)`
  — is what a Nyquist plot or a root locus needs, and it is the natural next
  step now that the per-block piece exists.
- **Choosing the operating point from the UI.** The API takes
  `operating_point`; the editor always sends the default. A picker (or "use the
  state at `t = T` from the last run") would make §3.3 a two-click fix instead of
  a curl command.
- **Trim.** `equilibrium()` solves for `x` at fixed `u`. Solving for both, subject
  to a target output, is the usual "trim" operation and is not implemented.
