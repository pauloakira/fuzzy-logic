# Ogata Example 8–1 — Ziegler–Nichols PID

A control design with a **published answer**, used here as a validation case for
the whole stack: the plant, the loop-transfer machinery, the stability margins,
and the PID block.

From *Modern Control Engineering*, 5th ed., §8-2, Example 8–1:

> Consider the control system shown in Figure 8–6 in which a PID controller is
> used to control the system.

The plant is `G(s) = 1/(s(s+1)(s+5))` under unity negative feedback. Because it
already contains an integrator, Ogata applies the **second** Ziegler–Nichols
method: raise a proportional gain until the loop sustains oscillation, then read
the tuning off `Kcr` and `Pcr`.

## What Ogata derives by hand, and what we get

He sets `Ti = ∞`, `Td = 0`, writes the characteristic equation
`s³ + 6s² + 5s + Kp = 0`, and applies Routh's criterion; then substitutes
`s = jω` to find the oscillation frequency.

We instead break the loop at the plant input, take `L(jω)` numerically, and read
the gain margin and phase crossover — a completely different route:

| | Ogata (Routh, by hand) | `fuzzy.analysis` |
|---|---|---|
| Critical gain `Kcr` | 30 | **30.0000** |
| Oscillation frequency | `√5` = 2.2361 rad/s | **2.2361** |
| Period `Pcr = 2π/ω` | 2.8099 s | **2.8099** |
| `Kp = 0.6·Kcr` | 18 | **18.0000** |
| `Ti = 0.5·Pcr` | 1.405 | **1.4050** |
| `Td = 0.125·Pcr` | 0.35124 | **0.35124** |
| `kd = Kp·Td` | 6.3223 | **6.3223** |

and the unit-step response overshoots **61.8%**, against the book's
"approximately 62%".

## The one thing that is not a free lunch

`PIDBlock` defaults to **derivative-on-output**, which is what a practical loop
uses — it avoids differentiating the discontinuity at a setpoint step. Ogata's
`Gc(s) = Kp(1 + 1/(Ti s) + Td s)` differentiates the **error**, which puts a
double zero at `s = -1.4235` in the forward path.

Same poles, different closed-loop zeros, and it matters:

| `derivative_on` | overshoot |
|---|---|
| `"error"` (Ogata's ideal form) | **61.8 %** |
| `"output"` (practical default) | 75.6 % |

So this diagram sets `derivative_on: "error"` explicitly. Reproducing a
published Ziegler–Nichols design with the practical form would not have matched,
and the mismatch would have looked like a bug in the simulation rather than a
difference between two controllers.

Ogata goes on to fine-tune this design down to about 18% overshoot (§8-2,
Figure 8–12); that refinement is not reproduced here.

## Running it

```bash
uvicorn editor.api:app --reload
```

then open `exercises/ogata_example_8_1/diagram.json` from the Diagrams list, set
the stop time to 16 s and the step to 2e-4, and Run. The numbers above are
pinned in `tests/integration/test_ogata_example_8_1.py`.
