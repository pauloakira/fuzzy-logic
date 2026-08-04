# Output charts for simulation results

What the results chart drawn by `editor/static/plot.js` shows, why its axis
rendering was changed, and the catalogue of charts a control tool of this kind
should output — chosen from Ogata and styled after Simulink. Written 2026-08-03,
when the tick-label distortion was fixed.

The two references are not equals, and they answer different questions.
**Ogata is the authority on *which* charts matter and *what each one means*** for
analysing a control system. Simulink — specifically its Scope block and the LTI
/ Linear System Analyzer viewers — is a widely-known implementation of how those
charts are *drawn* interactively, and it answers questions Ogata never has to (a
plot that fills a resizable panel, tick labels that must stay legible at any
width, a scope you can toggle signals on). Where they overlap, Ogata decides the
content and Simulink decides the interactive presentation.

- Ogata, *Modern Control Engineering*, 5th ed., Prentice Hall, 2010: §5
  "Transient and Steady-State Response Analysis", §6 "Root-Locus Analysis", §7
  "Frequency-Response Methods". The classical-control note in
  [`research-classical-control.md`](research-classical-control.md) follows the
  same edition.
- MathWorks documentation:
  [Scope block](https://www.mathworks.com/help/simulink/slref/scope.html),
  [`bode`](https://www.mathworks.com/help/control/ref/lti.bode.html),
  [`nyquist`](https://www.mathworks.com/help/control/ref/lti.nyquist.html),
  [`rlocus`](https://www.mathworks.com/help/control/ref/lti.rlocus.html),
  [`pzmap`](https://www.mathworks.com/help/control/ref/lti.pzmap.html).

---

## 1. The chart today

`editor/static/plot.js` draws a single chart: a multi-series time-domain line
plot of what `POST /api/simulate` returns. The response is `{ t, signals,
warnings, n_samples, returned }`, where `t` is the time vector and `signals` maps
each signal key to a value array of the same length; vector outputs are split per
component (`plant.y[0]`, `plant.y[1]`) in `editor/api.py`. The series drawn are
whichever keys the user has ticked in the `#signals` legend row.

Its current behaviour:

- **x-axis** is time in seconds, **y-axis** is signal amplitude, autoscaled to
  the combined range of the shown series with 6 % padding.
- A dashed **zero reference line** is drawn when zero lies inside the range — the
  natural datum for a controller error or command.
- Ticks are minimal: the y-axis is labelled at its min and max only, the x-axis
  at `t0` and `t1` (suffixed `s`). There are no interior gridlines.
- Data is **decimated server-side** to roughly two samples per device pixel
  (`max_points` in `run()`), so the browser never holds more than the plot can
  resolve.

This is the single most important chart in the tool: it is the **time response**
of the closed loop (Ogata §5), the trace a Simulink Scope shows. Everything below
is about drawing it correctly and about the charts that should join it.

## 2. The axis-label distortion and its fix

**Symptom.** On a wide plot the tick labels — `42.3`, `-2.4`, `0 s`, `40 s` —
were stretched horizontally into smeared, too-wide glyphs.

**Cause.** The SVG carried a *fixed* `viewBox` of `720 × 260` and was rendered
into a fluid, full-width element (`#plot { width: 100%; height: 260px }`) with
`preserveAspectRatio="none"`. `none` tells the browser to scale the viewBox to
the element on each axis independently. A panel ~1360 px wide gave a horizontal
scale of ≈ 1.9× against a vertical scale of 1.0× (the element is 260 px tall,
matching the viewBox), and that non-uniform scale is applied to *everything the
SVG contains, including text* — so every digit was stretched by ≈ 1.9× in x.

**Fix** (`editor/static/plot.js`, `editor/static/app.js`). Render in the
element's own pixel coordinates instead of a fixed viewBox:

- `renderPlot` now measures `root.clientWidth`/`clientHeight` when no explicit
  size is passed and sets the viewBox to that box, and the
  `preserveAspectRatio="none"` attribute is removed. One user unit is then one
  CSS pixel, the viewBox aspect equals the element aspect, and text is drawn at
  its true aspect ratio.
- A `ResizeObserver` on `#plot` re-draws (debounced with `requestAnimationFrame`)
  when the element resizes, so the viewBox stays matched as the panel width
  changes.

**Simulink reference.** A Scope and the LTI viewers draw tick labels at a fixed
font size that is independent of the plot-area shape; resizing the window moves
the gridlines but never distorts the numbers. The fix reproduces that property.

**Residual gaps vs Simulink** (tracked in the roadmap, §4): only the min/max y
ticks and the endpoint x ticks are shown, there are no interior gridlines, and
there is no in-axes axis title with units. The legend lives outside the axes as
the `#signals` checkbox row rather than as an overlaid key.

## 3. Which charts to output (Ogata)

The chart today is time-domain only, because `/api/simulate` returns only time
series. The analysis charts below are *not* derivable from a single time trace;
they need the model. The backend already carries it: `fuzzy/blocks.py`
`StateSpacePlant` holds `(A, B, C, D)` and exposes `eigenvalues()`, and
`fuzzy/lti.py` already works with these matrices. The frequency and pole
charts are therefore feasible with **NumPy only**, via
`H(jω) = C (jωI − A)^{-1} B + D`, with no new dependency.

The first two of these — the **Bode plot** and the **pole–zero map** (§3.2,
§3.4) — are now implemented. The numerics live in `fuzzy/analysis.py`
(frequency response by direct resolvent solves, poles by `eigvals`, transmission
zeros by the Faddeev–LeVerrier numerator plus `np.roots`); `POST /api/analyze`
runs them over every `StateSpacePlant` in the diagram and returns per-channel
Bode data, poles, and zeros; and `editor/static/analysis.js` draws both charts,
in pixel coordinates like `plot.js` so their labels are not stretched either.
The editor fetches the analysis alongside each run. When the diagram has no LTI
plant — for example the motor exercise, whose `MotorPlant` is nonlinear (a rate
limiter and hard state clamps, no `eigenvalues()`) — the panel shows a short note
saying so rather than silently disappearing, since a Bode plot and a pole–zero
map are defined only for a linear plant.

### 3.1 Time response — step, impulse, ramp (Ogata §5)

*Have* the general trace. *Missing* the canonical **unit-step response with
performance markers**: rise time, peak time and per-cent overshoot, settling
time, and steady-state error (Ogata §5-3). Axes: time [s] vs amplitude. These
four numbers are how §5 grades a design, and Simulink's step-response viewer
annotates them directly on the curve.

### 3.2 Frequency response (Ogata §7)

The family the request flagged as important.

- **Bode plot** *(implemented)* — magnitude [dB] and phase [deg] against **log**
  frequency [rad/s], in two stacked axes. Answers bandwidth, resonance, and —
  read at the gain- and phase-crossover frequencies — the **gain margin** and
  **phase margin** (Ogata §7-2, §7-6). One curve per plant output channel; the
  frequency grid auto-brackets the poles and zeros by two decades on each side.
- **Nyquist plot** — the polar locus of `L(jω)` in the complex plane, Re vs Im.
  Closed-loop stability follows from encirclements of `-1` (Ogata §7-6); the
  margins appear geometrically.
- **Nichols chart** — open-loop log-magnitude vs phase, from which the
  closed-loop magnitude is read off constant-M/N contours (Ogata §7-7).

### 3.3 Root locus (Ogata §6)

The loci of the closed-loop poles in the s-plane (Re vs Im) as a scalar gain
sweeps `0 → ∞`. Answers how damping, speed, and stability change with gain; the
crossing of the `jω` axis gives the ultimate gain `K_cr`, which ties directly to
the Ziegler–Nichols ultimate-cycle rule already described in
[`research-classical-control.md`](research-classical-control.md) §6.2.

### 3.4 Pole–zero map (Ogata §5-4, s-plane) *(implemented)*

A static s-plane plot of the plant poles (×) and per-channel transmission zeros
(○), with equal scale on both axes so distances read true. The poles are exactly
`StateSpacePlant.eigenvalues()`; dominant-pole damping ratio and natural
frequency are read from the angle and radius, explaining the transient shape the
time response shows.

Poles and zeros are attributed differently, because they belong to different
things. A pole is an eigenvalue of `A`, shared by every channel of the system —
drawn once, in the neutral foreground, labelled by system. A zero belongs to one
input/output channel: an SDOF plant's velocity channel has one at the origin
while its position channel has none, so a zero is drawn in **its channel's Bode
colour**. The two charts index one shared channel list precisely so that a
colour means the same channel on the s-plane as on the Bode plot.

### 3.5 Fuzzy-specific charts (not Ogata)

Distinct from the classical set and specific to this tool: the input/output
**membership functions**, the **rule-base activation**, and the 3-D **control
surface** (input error/rate → command). These are enumerated in
[`research-solid-mech-dynamics.md`](research-solid-mech-dynamics.md); recorded
here so the full output surface is in one place.

## 4. Roadmap

| Chart | Plots | Ogata | Needs | Status | Priority |
|---|---|---|---|---|---|
| Time response | time [s] vs amplitude | §5 | — | Done; axis rendering fixed (§2) | P0 |
| Bode | mag [dB] & phase [deg] vs log ω | §7-2 | `H(jω)` from `(A,B,C,D)` | **Done** (`/api/analyze`, `analysis.js`) | P1 |
| Pole–zero map | s-plane, Re vs Im | §5-4 | `eigenvalues()` | **Done** (`/api/analyze`, `analysis.js`) | P1 |
| Step response + markers | time vs amplitude, annotated | §5-3 | metrics on the step trace | Not started | P2 |
| Nyquist | Re vs Im of `L(jω)` | §7-6 | `H(jω)` | Not started | P2 |
| Root locus | s-plane vs gain | §6 | gain sweep, closed-loop eig | Not started | P2 |
| Nichols | log-mag vs phase | §7-7 | `H(jω)` | Not started | P3 |
| Fuzzy MFs / rules / surface | see §3.5 | — (fuzzy) | fuzzy block internals | Partly elsewhere | P3 |

Interior gridlines, in-axes axis titles with units, and an overlaid legend for
the time-response chart (the §2 residual gaps) ride along as P2 presentation
work, since every chart above wants the same axis furniture.

## 5. Shared styling conventions (Simulink-derived)

Every chart added should share the axis conventions of the time-response chart so
the output surface reads as one tool:

- **Tick labels are drawn at a fixed pixel size and never stretched** — render in
  the element's pixel coordinates (§2), not a `viewBox` scaled with
  `preserveAspectRatio="none"`.
- **Interior gridlines**, light, plus axis titles carrying units (`[s]`, `[dB]`,
  `[deg]`, `[rad/s]`). Frequency axes are **log-scaled** and magnitude is in
  **dB**, as a Bode plot requires.
- The existing `PALETTE` and per-series colours (`colourFor`) carry across
  charts; reference and zero lines stay dashed.
- Time series honour the server-side decimation. Analysis charts (Bode, Nyquist,
  locus) are instead computed on a **dense internal frequency or gain grid** —
  they are functions of the model, not of the simulated trace, and must not be
  decimated to the sim's sample count.
