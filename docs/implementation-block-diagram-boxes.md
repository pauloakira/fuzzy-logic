# Block symbols on the canvas

The drawing convention used by `editor/static/canvas.js`, why each choice was
made, and where it agrees or disagrees with the two references it was checked
against. Written 2026-08-03, when the nodes were restyled.

The two references are not equals. **Ogata is the authority on what a block
diagram *means*;** Simulink is a widely-known implementation of that meaning in
an interactive editor, and it answers questions Ogata never has to (a diagram
with a hundred blocks, blocks you can click, blocks whose parameters you edit).
Where they disagree, this document says so and gives the reason for the pick.

- Ogata, *Modern Control Engineering*, 5th ed., §2–3 "Automatic Control
  Systems" (pp. 17–27) and §2–4 "Modeling in State Space" (Figure 2–16, p. 33).
- MathWorks Simulink documentation:
  [element names and labels](https://www.mathworks.com/help/simulink/ug/configure-model-element-names-and-labels.html),
  [Sum block](https://www.mathworks.com/help/simulink/slref/sum.html).

---

## 1. What Ogata actually specifies

§2–3 is short, and almost all of it is prescriptive. In full:

| Element | Ogata's symbol | Ogata's words |
|---|---|---|
| Block | rectangle | "a symbol for the mathematical operation on the input signal to the block that produces the output. The transfer functions of the components are usually entered in the corresponding blocks" |
| Signal | arrow | "connected by arrows to indicate the direction of the flow of signals… the signal can pass only in the direction of the arrows" |
| Summing point | circle with a cross, ⊗ | "a circle with a cross is the symbol that indicates a summing operation. The plus or minus sign at each arrowhead indicates whether that signal is to be added or subtracted" |
| Branch point | solid dot on the wire | "a point from which the signal from a block goes concurrently to other blocks or summing points" |

Two things that are *not* in the list matter as much as what is.

**There is no separate symbol for a gain.** Figure 2–16 — the block diagram of a
mass-spring-damper in state-space form — draws `1/m`, `b/m` and `k/m` as plain
rectangles, exactly like every other block, and the integrators as rectangles
containing `∫`. No triangles appear anywhere in the book. The triangle comes
from analog-computer and signal-flow-graph practice; the 5th edition dropped
signal flow graphs entirely ("in order to provide space for more important
subjects"), so this book has one shape vocabulary and the triangle is not in it.

**A block's contents are its operation, not its identity.** Ogata writes `G(s)`,
`1/Cs`, `k/m` inside the box. Where the transfer function is not the point he
writes the *role* instead — Figure 2–6 has boxes reading "Amplifier",
"Actuator", "Plant", "Sensor". Either way the text inside answers *what does
this do*. The block has no name of its own; the figure caption identifies it.

---

## 2. The convention this editor uses

### 2.1 The outline says what kind of block it is

| Shape | Block types | Reference |
|---|---|---|
| Rectangle | everything not listed below | Ogata ✓, Simulink ✓ |
| Circle | `Sum` | Ogata ✓ (but see §3.1), Simulink ✓ |
| Triangle, pointing along the flow | `Gain`, `StateFeedback` | Ogata ✗, Simulink ✓ (see §3.2) |

### 2.2 The face carries the operation

Ogata's rule, applied to blocks that are mostly not LTI and therefore have no
`G(s)` to write:

| Block | Face | Note |
|---|---|---|
| `StateSpacePlant` | `x' = Ax+Bu` / `y = Cx+Du` | the operation, as Ogata writes `1/Cs` |
| `MotorPlant` | `ω' = k·V − ω` / `V' = u` | the rate limit and state clamps are omitted; an icon is not a specification |
| `Observer` | `x̂' = Ax̂+Bu` / `+ L(y−Cx̂)` | |
| `Gain` | the value of `k`, or `K` for a matrix | |
| `StateFeedback` | `−K·x` | |
| `Constant` | the value | |
| `Select` | `u[i]` | |
| `Harmonic`, `Step`, `Saturation` | a line drawing of the signal or the characteristic | Simulink only; Ogata's book is linear and has no saturation symbol |
| `FISBlock` | `FIS` / `Mamdani` | a role name, as Ogata's "Amplifier" |
| `PIDBlock` | `PID` | a role name |
| anything unregistered | its type name | the fallback is Ogata's Figure 2–6 case |

### 2.3 The name goes below the block

Simulink's rule for a block whose ports are on its sides. It exists because an
editor needs a per-instance identity that a textbook figure does not: the wires
in `diagram.json` are `["plant", "y"] → ["controller", "x"]`, and you cannot
select a block to edit its parameters without knowing which one you clicked.
Ogata's blocks have no names because his figures have five blocks and a caption.

Putting the name *below* rather than inside is what frees the face for §2.2. The
class name is no longer drawn at all — it is on the `data-type` attribute, and
it is visible in the parameter panel when a block is selected.

### 2.4 Signals

Arrowheads at the destination, orthogonal routing, one wire per connection.
Ogata's unilateral-flow rule, and the reason a wired input hides its port dot:
the dot was painted over the arrowhead, so no wire had a visible direction. An
*unwired* input still shows its dot, because there it is a drop target rather
than a signal.

### 2.5 Sum signs

`+` or `−` beside each input port, from the block's `signs` parameter. This is
Ogata's rule verbatim — "the plus or minus sign at each arrowhead" — and also
how Simulink renders its "List of signs" parameter.

### 2.6 Sampled blocks

A small `Ts` in the top corner of `FISBlock`, `PIDBlock` and `StateFeedback` —
the blocks whose `discrete` flag is set, which are sampled at the control rate
and zero-order-held between samples.

Simulink's convention: annotate the rate, do not change the shape. Ogata has no
convention here at all; the 5th edition is a continuous-time book. This replaced
an earlier rendering in which a sampled block was drawn as a stadium, which
spent the shape vocabulary — needed for §2.1 — on a property that is not the
kind of thing a block is.

---

## 3. Where this diverges from Ogata, and why

### 3.1 The summing point has no cross

Ogata's symbol is ⊗ — a circle with a cross through it. This editor draws a
plain circle, following Simulink's round Sum block.

Reason: at the sizes an on-screen diagram actually uses, the cross collides with
the `+`/`−` signs, which are the informative part. Ogata's Figure 2–2 has one
summing point on a full text page; `ex2_sdof_fuzzy` has one at 52 px tall
alongside six other blocks. When only one of the two marks fits, the signs are
the one that carries information — the cross only repeats what the shape already
says.

Cheap to reverse if it turns out to matter: it is two lines in `nodePath()`.

### 3.2 A gain is a triangle

Ogata boxes gains (§1). This editor draws them as triangles, following Simulink.

Reason: Ogata's diagrams are read once, at leisure, with the caption and the
surrounding equations in view. An editor's diagram is scanned repeatedly while
being manipulated, and a distinct silhouette is worth more there than
consistency with the book — you can find every gain in a diagram without reading
any of the labels. The triangle also points along the signal flow, which
duplicates the arrow direction at a glance.

This is the one deliberate departure from the reference on a point Ogata is
explicit about. It is a legibility trade, not a correction.

### 3.3 There are no branch points

Ogata names the branch point as one of the three things a block diagram is made
of ("Any linear control system may be represented by a block diagram consisting
of blocks, summing points, and branch points"), and draws it as a solid dot
where one signal feeds several destinations.

This editor has no branch points. An output feeding three inputs is drawn as
three separate wires leaving the same port, which is the same *topology* but not
the same *picture* — Ogata's single trunk with a dot says "one signal" where
three parallel lines say "three signals that happen to start together".

**This is a genuine gap, not a trade.** It is recorded in `docs/future-work.md`
alongside the other routing gap (no obstacle avoidance — a wire will currently
cross a block that sits in its way).

### 3.4 Wires are not labelled

Ogata labels the arrows: `R(s)`, `E(s)`, `C(s)`, `B(s)`. This editor labels
neither the wire nor the port on the canvas; a wire's endpoints are in its
`data-wire` attribute and in the selection panel, and the signal names appear in
the plot legend after a run.

Reason: Ogata's names are the variables of the algebra he is about to do, and
his diagrams have four of them. Here the equivalent — `plant.y[0]`,
`actuator.y` — is generated from the block name and port, so drawing it on the
wire would repeat what the block labels already say and roughly double the text
on the canvas. Worth revisiting if diagrams get large enough that tracing a wire
by eye becomes the bottleneck.

---

## 4. Summary

| Convention | Ogata §2–3 | Simulink | Here |
|---|---|---|---|
| Block is a rectangle | ✓ | ✓ | ✓ |
| Operation drawn inside the block | ✓ | ✓ | ✓ |
| Role name inside when the operation is not the point | ✓ (Fig. 2–6) | ✓ | ✓ |
| Arrow shows direction; flow is unilateral | ✓ | ✓ | ✓ |
| Summing point is a circle | ✓ | ✓ | ✓ |
| …with a cross through it | ✓ | ✗ | ✗ (§3.1) |
| `+`/`−` at each summing input | ✓ | ✓ | ✓ |
| Gain has its own shape | ✗ | ✓ triangle | ✓ triangle (§3.2) |
| Block carries an instance name | ✗ | ✓ below | ✓ below (§2.3) |
| Sample time annotated, not shaped | — | ✓ | ✓ |
| Branch point as a junction dot | ✓ | ✓ | ✗ (§3.3) |
| Signals labelled on the wire | ✓ | optional | ✗ (§3.4) |

Three divergences, one of which (§3.3, branch points) is a gap to close rather
than a decision to defend.

---

## 5. Where this lives in the code

- `SHAPE`, `icon()`, `GLYPHS`, `nodePath()`, `nodeIcon()` — `editor/static/canvas.js`
- `portPosition()` — same file; solves for the circle boundary on a `Sum`, so a
  wire ends *on* the summing point rather than on its bounding box
- `.node-face`, `.node-eq`, `.node-name`, `.node-ts`, `.port-sign`,
  `.port[data-wired]` — `editor/static/style.css`
- Tests — `tests/e2e/test_canvas.py`, under "nodes": the outline per block kind,
  the name below the shape, the equation on the face, the sum's signs, and the
  `Ts` annotation
