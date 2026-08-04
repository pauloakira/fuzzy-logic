# Future work

What is deferred, what state it is actually in, and where to pick it up. Written
2026-08-02, after the block-diagram core, the declarative FIS layer, and the
editor API landed.

**The headline: the fuzzy logic itself is the thread to come back to.** The last
several phases were infrastructure — a simulation core, a spec layer, LQR and
observer design, CI, an HTTP API. That infrastructure exists to serve fuzzy
research, and the gap between what this repo *documents* about fuzzy logic and
what it *implements* has widened while the plumbing was built. §1 is that gap.

---

## 1. Fuzzy logic — the main thread

### 1.1 ANFIS and the neuro-fuzzy track (confirmed still in scope)

`fuzzy/anfis.py` is **one docstring line**. Nothing exists.

Meanwhile `docs/research-fuzzy-logic.md` mentions ANFIS 36 times and covers the
architecture, the hybrid learning rule, and numerical pitfalls; the README
advertises it; and all three agent contracts in `.claude/agents/` are written
around a PyTorch neuro-fuzzy track. This is the single largest gap between the
stated project and the built one.

Entry point: `torch` is already declared as the `[anfis]` optional extra and is
deliberately not installed. A Sugeno/TSK inference system (§1.2) is the natural
prerequisite — ANFIS *is* a trainable TSK system, so building TSK first makes
ANFIS an extension rather than a from-scratch effort.

Worth knowing: phase 4 made membership functions and rule bases into data
(`Term`, `Variable`, `RuleBase`, `FISSpec`). ANFIS needs exactly that structure to
expose MF parameters as trainable tensors, so the groundwork is unusually good.

### 1.2 Sugeno and Tsukamoto inference

`fuzzy/fis.py` opens with *"Mamdani (currently), Sugeno and Tsukamoto to come."*
Neither exists. `docs/research-fuzzy-logic.md` §25 derives Tsukamoto and Part I
covers Sugeno with a Mamdani-vs-Sugeno comparison table.

A TSK system with linear consequents is also the bridge to state-space control
that `research-classical-control.md` gestures at: TSK with linear consequents is
gain-scheduled linear feedback under another name, which makes the fuzzy/LQR
comparison a much sharper story than Mamdani-vs-PID was.

### 1.3 `fuzzy/operators.py` is dead code

37 lines defining `t_min`, `s_max`, `t_product`, `s_probabilistic`,
`standard_complement`. **Nothing imports it.** `MamdaniFIS.evaluate_full`
hardcodes Python's `min` and `np.minimum`/`np.maximum`, so the pluggable t-norm
design the module docstring advertises does not actually work — swapping in the
product t-norm requires editing `fis.py`.

Either wire it into `MamdaniFIS` (a `t_norm`/`s_norm` parameter, defaulting to
min/max so nothing changes) or delete it. Right now it is a promise the code does
not keep. Wiring it in is the better option: `docs/research-fuzzy-logic.md` §27
covers t-norm families, and ANFIS conventionally uses the *product* t-norm, so
§1.1 will need this anyway.

### 1.4 Defuzzification beyond the centroid

`fuzzy/defuzz.py` implements `centroid` and nothing else. §31 of the research
note gives formulas for bisector, mean-of-maxima, smallest-of-maxima, and
largest-of-maxima.

This is not academic here. `REPORT.md` §11 records that centroid defuzzification
caps the attainable command at ±2.505 N of a declared ±3 N actuator — the
controller *cannot* reach its own stated authority. Mean-of-maxima would not have
that limitation, so implementing the alternatives turns a documented limitation
into a comparable design choice.

### 1.5 Membership-function kinds

Registry has triangular, trapezoidal, left/right shoulder, gaussian. The research
note also describes **bell** and **sigmoid** MFs. Both are a few lines each and
would drop straight into `MF_REGISTRY` — and generalised-bell MFs are the
conventional choice for ANFIS.

### 1.6 Refining the controllers

`Variable.partition()` now generalises to any term count, so the "7 or 9 terms
would refine resolution" future work in `REPORT.md` §11 is a one-argument change.
Nobody has run it. Cheap, and it directly tests a published claim.

---

## 2. Control-theory studies — tools built, studies not run

Phase 5 built `fuzzy/lti.py` (`lqr`, `observer_gain`, `solve_care`) and the
`Observer` block, with tests. **No study uses them.**

### 2.1 LQR as an honest benchmark

The exercise-2 comparison pits fuzzy against one hand-tuned PID. LQR is the
*optimal* linear state-feedback law for a given cost, which is a far more
defensible baseline. Roughly 30 lines on top of what exists.

### 2.2 Observer in the loop

Every controller in the study currently receives **perfect velocity**, which no
real displacement sensor provides. Putting the `Observer` in the loop makes
estimation error part of the result instead of assuming it away — the single
biggest gap between the exercise and a real active-vibration rig.

Deliberately deferred rather than dropped: the observer changes the *fuzzy*
numbers too, so it re-frames a comparison that has already been submitted and
carries an errata. Decision on record (2026-08-02): write it as a separate
`REPORT_observer.md` and leave the submitted comparison intact.

### 2.3 Multi-DOF plant

`docs/research-solid-mech-dynamics.md` §5 already writes the multi-DOF building
model as `M x'' + C x' + K x = -M·1·x_g'' + B u`. That is state-space form, so it
is a `StateSpacePlant` with bigger matrices — no new machinery needed.

---

## 3. The block editor — what is left after phase 7

Phase 7 is complete: 7a structured errors, 7b HTTP API, 7c canvas rendering, 7d
interactive editing, 7e run-and-plot, 7f the fuzzy controller editor.
`docs/design-block-diagram-simulation.md` §13 has the breakdown; the drawing
convention and its two references are in
`docs/implementation-block-diagram-boxes.md`.

What that convention does not yet implement:

### 3.1 No branch points

Ogata names the branch point as one of the three elements a block diagram is
made of, and draws it as a solid dot where one signal feeds several
destinations. This editor draws an output that feeds three inputs as three
separate wires leaving the same port — the same topology, a different picture.
Simulink and Ogata agree here and the editor is the odd one out.

The work is in `renderDiagram()`: group connections by source port, route one
trunk, and drop a junction dot where each branch leaves it. The wire hit-testing
and selection then need to distinguish a branch from the trunk.

### 3.2 No obstacle avoidance in routing

`routePoints()` routes orthogonally and gives each feedback wire its own lane
below the blocks it joins, but it does not know where the other blocks are. In
`ex2_sdof_fuzzy` the feedback wires cross the `actuator` block. Visible in the
editor today.

### 3.3 One unidentified browser-test flake

One failure in five full runs of `tests/e2e`, not reproduced in many runs since
and never captured. Recorded so it is not rediscovered as new.

---

## 4. Smaller debts

- **`defuzz.centroid` assumes a uniformly spaced universe.** It computes
  `sum(y*mu)/sum(mu)` with no `dx` weighting — correct only on a uniform grid,
  and the docstring does not say so. Silent wrong answers on a non-uniform
  universe.
- **Figures are not guarded against drift.** `diagram.json` and `diagram.mmd`
  have drift tests; the PNGs do not, and cannot easily, since their bytes are
  platform-dependent. A stale `frequency_response.png` went unnoticed once.
- **Report language is mixed** — English prose, Portuguese plot labels and
  variable names (`deslocamento`, `Aceleração`). Deliberate for the course, but
  unresolved.
- **`ruff format` is not gated in CI**, because it would flatten the rule
  matrices' manual column alignment. Recorded in the README as a decision rather
  than an oversight.
- **`examples/` is still empty** — a README and no scripts. The README's
  convention section describes files that do not exist.
