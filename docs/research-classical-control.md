# Classical Control: PD, PI, and PID Controllers — A Theoretical Note

This note develops, in a mathematically rigorous and impersonal style, the theory of the classical single-input single-output (SISO) feedback controllers most widely deployed in practice: the proportional–derivative (PD), proportional–integral (PI), and proportional–integral–derivative (PID) controllers. The exposition follows the treatment in K. Ogata, *Modern Control Engineering*, 5th ed., Prentice Hall, 2010 (hereafter referred to as Ogata), with explicit cross-references to Chapters 2, 5, and 8, and is complemented by primary research literature on tuning rules, anti-windup, derivative filtering, and Internal Model Control (IMC) design.

---

## 1. Preliminaries and Notation

### 1.1 Linear time-invariant SISO setting

Throughout this note, the plant is assumed to be a linear time-invariant (LTI) SISO system with input `u(t)`, output `y(t)`, and rational transfer function

```
G_p(s) = Y(s) / U(s),
```

where `s ∈ ℂ` is the Laplace variable. Lowercase letters denote time-domain signals, and uppercase letters denote their unilateral Laplace transforms; zero initial conditions are assumed unless stated otherwise.

A unity-feedback closed-loop configuration is considered:

```
        +--------+      +--------+
 r(t) ─►│ Σ ─e──►│ G_c(s)│ ─u──►│ G_p(s) │ ──► y(t)
        ▲ (-)    +--------+      +--------+
        └────────────────────────────────┘
```

with reference `r(t)`, controller `G_c(s)`, error `e(t) = r(t) − y(t)`, manipulated variable `u(t)`, and output `y(t)`. The closed-loop transfer function from `r` to `y` is

```
T(s) = G_c(s) G_p(s) / [1 + G_c(s) G_p(s)],
```

and the sensitivity function is

```
S(s) = 1 / [1 + G_c(s) G_p(s)] = E(s)/R(s).
```

### 1.2 Industrial classification of controllers

Ogata (Section 2-3) classifies industrial controllers, by control action, as: two-position (on–off), proportional (P), integral (I), proportional-plus-integral (PI), proportional-plus-derivative (PD), and proportional-plus-integral-plus-derivative (PID). All of the latter five are *linear* control laws and admit a transfer-function description.

---

## 2. The Three Elementary Control Actions

The PID family is built from three elementary actions whose time-domain laws and transfer functions are now stated.

### 2.1 Proportional action (P)

The proportional control law is

```
u(t) = K_p · e(t),         U(s)/E(s) = K_p,
```

where `K_p > 0` is the *proportional gain* (Ogata, p. 24). A proportional controller is, in essence, a frequency-independent amplifier of the actuating error.

### 2.2 Integral action (I)

The integral control law is defined either by the rate equation `u̇(t) = K_i · e(t)` or, equivalently in integrated form,

```
u(t) = K_i ∫₀ᵗ e(τ) dτ,     U(s)/E(s) = K_i / s.
```

The defining feature is that `u(t)` may be nonzero while `e(t) = 0`, since the controller "remembers" past error through the integrator (Ogata, Fig. 5-36). This memory enables the controller to eliminate steady-state error against constant disturbances and references, at the cost of introducing an additional pole at the origin and therefore a 90° phase lag at all frequencies.

### 2.3 Derivative action (D)

A pure derivative action `u(t) = K_d · ė(t)` has transfer function `K_d s`. The derivative term is *anticipatory*: it reacts to the rate of change of the error and produces a corrective output before the error magnitude becomes large, thereby adding damping to the closed loop (Ogata, p. 222). Pure derivative action is never used in isolation, since it produces no response to a constant error and amplifies high-frequency measurement noise without bound.

---

## 3. The PD Controller

### 3.1 Definition

The proportional-plus-derivative (PD) controller is defined in the time domain by

```
u(t) = K_p e(t) + K_p T_d ė(t),
```

with transfer function

```
G_c(s) = K_p (1 + T_d s),
```

where `T_d ≥ 0` is the *derivative time* (Ogata, p. 25). The controller introduces one finite zero at `s = −1/T_d` and no additional pole.

### 3.2 Effect on a pure inertia plant

A canonical pedagogical example (Ogata, §5-7) is the inertia plant `G_p(s) = 1/(J s²)`. Under proportional control alone the closed-loop characteristic polynomial is

```
J s² + K_p = 0,
```

whose roots `s = ± j √(K_p/J)` are purely imaginary. The unit-step response is a *sustained, undamped oscillation*, which is unacceptable.

Under PD control the characteristic polynomial becomes

```
J s² + K_p T_d s + K_p = 0,
```

with damping ratio

```
ζ = (T_d / 2) · √(K_p / J)  > 0   for any   T_d > 0.
```

Hence derivative action introduces damping that the original system lacked. This is the precise sense in which PD "stabilises" the inertial plant.

### 3.3 PD on a second-order plant with viscous friction

For the plant `G_p(s) = 1/[s (J s + B)]` controlled by the PD law `K_p (1 + T_d s)`, equivalently written as `(K_p + K_d s)` with `K_d = K_p T_d`, the closed-loop characteristic equation is

```
J s² + (B + K_d) s + K_p = 0,
```

so that the *effective damping coefficient* increases from `B` to `B + K_d`. The damping ratio is

```
ζ = (B + K_d) / (2 √(K_p J)).
```

The steady-state error to a unit-ramp input is

```
e_ss = B / K_p,
```

independent of `K_d` (Ogata, p. 224). It follows that:

1. Derivative action does not directly alter the steady-state error.
2. Derivative action permits larger values of `K_p` (and therefore smaller `e_ss` for ramp inputs) while preserving an acceptable damping ratio.
3. A standard design recommendation (Ogata, p. 225) is to choose `B` small, `K_p` large, and `K_d` such that `ζ ∈ [0.4, 0.7]`.

### 3.4 Practical note on the derivative term

A physically realisable derivative action requires a low-pass filter to roll off the high-frequency gain. The standard filtered form is

```
G_d(s) = K_d s / (1 + (T_d / N) s),
```

with the filter constant typically chosen as `N ∈ [2, 20]`; see Åström and Hägglund (1995). Without such filtering, the controller amplifies measurement noise and is not strictly proper, complicating implementation in analogue hardware and in discrete-time digital implementations.

---

## 4. The PI Controller

### 4.1 Definition

The proportional-plus-integral (PI) controller is defined by

```
u(t) = K_p e(t) + (K_p / T_i) ∫₀ᵗ e(τ) dτ,
```

with transfer function

```
G_c(s) = K_p (1 + 1/(T_i s)) = K_p (T_i s + 1) / (T_i s),
```

where `T_i > 0` is the *integral (or reset) time* (Ogata, p. 24). The PI controller introduces one zero at `s = −1/T_i` and one pole at the origin. The pole at the origin is the key structural feature: it raises by one the *type* of the open-loop transfer function `L(s) = G_c(s) G_p(s)`.

### 4.2 Steady-state error and the type-number argument

For a unity-feedback loop with open-loop transfer function

```
L(s) = K (T_a s + 1)(T_b s + 1) ⋯ / [s^N (T_1 s + 1)(T_2 s + 1) ⋯],
```

the static error constants (Ogata, §5-8) are

```
K_p^* = lim_{s→0} L(s),         (position)
K_v   = lim_{s→0} s L(s),       (velocity)
K_a   = lim_{s→0} s² L(s).      (acceleration)
```

The corresponding steady-state errors of a unity-feedback loop driven by canonical inputs are summarised in Table 1.

| Input             | Type 0           | Type 1            | Type 2     |
| ----------------- | ---------------- | ----------------- | ---------- |
| Step (`1/s`)      | `1/(1+K_p^*)`    | `0`               | `0`        |
| Ramp (`1/s²`)     | `∞`              | `1/K_v`           | `0`        |
| Parabola (`1/s³`) | `∞`              | `∞`               | `1/K_a`    |

Adding integral action increases `N` by one and therefore eliminates the steady-state error of the loop against any input class whose error was previously finite-but-nonzero. This is the *raison d'être* of the integral term.

### 4.3 PI control of a first-order plant: error elimination

Consider a Type-0 plant `G_p(s) = K/(T s + 1)` under proportional control with gain unity. Then

```
E(s)/R(s) = (T s + 1) / (T s + 1 + K),
```

and the steady-state error to a unit step is `e_ss = 1/(K + 1) ≠ 0` (Ogata, p. 219). Replacing `K` by an integral controller `K/s` yields

```
E(s)/R(s) = s(T s + 1) / [T s² + s + K],
```

so that, by the final-value theorem, `e_ss = lim_{s→0} sE(s) = 0` for a unit-step reference, *provided* the closed-loop is stable. Integral control thus eliminates step offset, but converts a first-order loop into a second-order loop and may render the response oscillatory.

### 4.4 PI control under load disturbance

For the load element `1/[s(J s + B)]` with proportional controller `K_p` and a torque disturbance `D(s)`, the disturbance-to-output transfer function is

```
Y(s)/D(s) = 1 / (J s² + B s + K_p),       (P only)
```

and a step disturbance of magnitude `T_d` produces a *steady-state offset* (Ogata, p. 221)

```
y_ss = T_d / K_p.
```

Replacing `K_p` by `K_p (1 + 1/(T_i s))` (i.e. PI) gives

```
Y(s)/D(s) = s / [J s³ + B s² + K_p s + K_p / T_i],
```

and the factor `s` in the numerator forces `y_ss = 0` against any step disturbance (Ogata, pp. 221–222). The price paid is the conversion of a second-order loop into a third-order loop; large `K_p` may push closed-loop poles into the right half-plane and destabilise the system.

### 4.5 PI in the frequency domain

The PI controller has Bode magnitude `|G_c(jω)| = K_p √(1 + 1/(T_i ω)²)` and phase

```
∠G_c(jω) = arctan(T_i ω) − π/2.
```

At low frequency the magnitude grows as `1/ω` (boosting low-frequency gain and driving steady-state error to zero) and the phase asymptotes to `−π/2`, contributing to phase lag and reducing the phase margin. The zero at `s = −1/T_i` is the principal design degree of freedom: placing it well below the closed-loop bandwidth recovers most of the lost phase at crossover.

---

## 5. The PID Controller

### 5.1 Standard (textbook) form

The proportional-plus-integral-plus-derivative (PID) controller is defined by the time-domain law

```
u(t) = K_p e(t) + (K_p / T_i) ∫₀ᵗ e(τ) dτ + K_p T_d ė(t),
```

with transfer function

```
G_c(s) = K_p [1 + 1/(T_i s) + T_d s] = K_p (T_i T_d s² + T_i s + 1) / (T_i s).
```

This is the "ideal" or "standard" form (Ogata, p. 25, Eq. for §2-3). Equivalent parallel and parametric forms are

```
G_c(s) = K_p + K_i / s + K_d s,    with    K_i = K_p / T_i,    K_d = K_p T_d.
```

The ideal PID controller has one pole at the origin and two zeros given by the roots of `T_i T_d s² + T_i s + 1 = 0`.

### 5.2 Properties of the ideal PID

The ideal PID combines the qualitative effects of P, I, and D actions:

- The integral action removes steady-state error against step references and step disturbances (raises the open-loop type by one).
- The derivative action increases the closed-loop damping and improves transient performance.
- The proportional action provides the immediate, frequency-flat response and sets the basic loop gain.

The PID controller, when applied to a generic plant `G_p(s)`, raises the relative order of the loop transfer function `L(s) = G_c(s) G_p(s)` by `−1` (one extra pole at the origin) and lowers it by `2` (two extra zeros). For a strictly proper plant, the ideal PID is not strictly proper, so practical implementation requires filtering of the derivative term (Section 5.5).

### 5.3 The PID controller as a third-order modifier

Applying an ideal PID to a first-order-plus-dead-time plant of the form

```
G_p(s) = (K e^{−L s}) / (T s + 1),
```

produces a closed-loop characteristic equation that is, after Padé approximation of the dead time, of order three or higher. This is the principal tractable model used in the derivation of empirical tuning rules described below.

### 5.4 Block-diagram representations

Three structurally distinct realisations of the PID action are commonly encountered:

1. **PID (textbook form)**, in which P, I, and D all act on the error `e = r − y`. This is the form analysed above and corresponds to Ogata, Fig. 8-1. The chief drawback is the *set-point kick*: a step in `r` produces a Dirac impulse in the control signal through the derivative term.
2. **PI-D control** (Ogata, Fig. 8-26), in which the derivative action operates only on the measured output `y` (i.e. on the negative of the feedback signal `b = y`), removing the impulse caused by step references while preserving the disturbance rejection of the full PID. The manipulated signal is

   ```
   U(s) = K_p (1 + 1/(T_i s)) R(s) − K_p (1 + 1/(T_i s) + T_d s) Y(s).
   ```

3. **I-PD control** (Ogata, Fig. 8-27), in which only the integral action operates on the error and both proportional and derivative actions operate on `y`. The reference enters only through the integrator:

   ```
   U(s) = K_p (1 / (T_i s)) R(s) − K_p (1 + 1/(T_i s) + T_d s) Y(s).
   ```

   Such structures move toward what Ogata calls *two-degrees-of-freedom* control, since the response to references and the response to disturbances are no longer constrained to share the same shape.

For all three structures the transfer function from disturbance `D(s)` to output `Y(s)` is identical, namely

```
Y(s) / D(s) = G_p(s) / [1 + K_p G_p(s) (1 + 1/(T_i s) + T_d s)],
```

so the disturbance rejection properties are preserved.

### 5.5 Realisable form and derivative filtering

The ideal derivative `T_d s` is non-causal and amplifies high-frequency noise. A first-order roll-off is therefore introduced (Åström and Hägglund, 1995):

```
G_c^{realisable}(s) = K_p [1 + 1/(T_i s) + T_d s / (1 + (T_d / N) s)],
```

with `N` typically chosen in `[2, 20]`. The filter limits the high-frequency gain of the derivative term to `K_p · N`. A common alternative is the *series* (or *interacting*) form

```
G_c^{series}(s) = K'_p (1 + 1/(T'_i s)) (1 + T'_d s) / (1 + α T'_d s),
```

with the tuning parameter `α` (`0 < α ≪ 1`). The series form is historically associated with pneumatic and analogue electronic implementations.

### 5.6 Anti-windup and saturation

When the actuator saturates, the integral term may continue to accumulate error, producing a phenomenon known as *integrator windup*. After the error sign reverses, the output remains saturated for an extended period until the integrator unwinds, producing large overshoots. Two practical anti-windup schemes are widely used (cf. *Anti-Windup Schemes*, MathWorks documentation, 2024):

1. **Conditional integration (clamping):** the integration is frozen whenever the unsaturated control output and the error have the same sign and the actuator is at a limit.
2. **Back-calculation (tracking anti-windup):** the difference between the unsaturated and the saturated control signal is fed back to the integrator through a gain `1/T_t`, so that the integrator state is dynamically driven toward a value compatible with the saturation limits:

   ```
   ẋ_I = (K_p / T_i) e + (1/T_t) (u_sat − u),
   ```

   where `x_I` is the integrator state, `u` is the unsaturated control, and `u_sat` is the saturated control.

Both schemes preserve the linear behaviour in the unsaturated region and only modify the integrator dynamics inside the saturation set.

---

## 6. Tuning Rules

Because the parameters `(K_p, T_i, T_d)` cannot be derived from physical first principles for plants of unknown structure, *tuning rules* play a central role in practice. Ogata, §8-2 presents the two original Ziegler–Nichols (ZN) rules; the IMC family of rules due to Rivera, Morari, and Skogestad has come to dominate process control practice.

### 6.1 Ziegler–Nichols, first method (reaction-curve method)

A unit-step is applied to the plant in open loop. If the response is S-shaped and free of integrators or dominant complex poles, it is approximated by the first-order-plus-dead-time (FOPDT) model

```
G_p(s) ≈ K e^{−L s} / (T s + 1),
```

where `L` and `T` are read from the inflection-tangent intersections with the time axis and with the asymptote `c = K`, respectively. The recommended settings are (Ogata, Table 8-1):

| Controller | `K_p`         | `T_i`     | `T_d`     |
| ---------- | ------------- | --------- | --------- |
| P          | `T/L`         | `∞`       | `0`       |
| PI         | `0.9 T/L`     | `L/0.3`   | `0`       |
| PID        | `1.2 T/L`     | `2 L`     | `0.5 L`   |

The PID controller obtained by this rule is

```
G_c(s) = 0.6 T (s + 1/L)² / s,
```

which has a pole at the origin and a *double zero* at `s = −1/L`. This particular form was advocated by Ziegler and Nichols (1942) for processes with measurable transport lag and is the historical origin of the family of "self-tuning" rules.

### 6.2 Ziegler–Nichols, second method (ultimate-cycle method)

The integral and derivative actions are disabled (`T_i = ∞`, `T_d = 0`) and the proportional gain `K_p` is increased from zero until the closed loop exhibits a *sustained* oscillation with critical gain `K_cr` and period `P_cr`. The recommended settings are (Ogata, Table 8-2):

| Controller | `K_p`            | `T_i`           | `T_d`         |
| ---------- | ---------------- | --------------- | ------------- |
| P          | `0.5 K_cr`       | `∞`             | `0`           |
| PI         | `0.45 K_cr`      | `(1/1.2) P_cr`  | `0`           |
| PID        | `0.6 K_cr`       | `0.5 P_cr`      | `0.125 P_cr`  |

For a known plant `G_p(s)`, the pair `(K_cr, P_cr)` may be computed analytically: `K_cr` is the gain that places a pair of closed-loop poles on the imaginary axis (the value at which Routh's criterion gives a zero in the first column), and `P_cr = 2π/ω_cr`, where `ω_cr` is the corresponding crossover frequency. Equivalently, `K_cr` and `ω_cr` are read from the intersection of the root locus with the `jω` axis.

The PID controller obtained by the second method is

```
G_c(s) = 0.075 K_cr P_cr (s + 4/P_cr)² / s,
```

a controller with a pole at the origin and a double zero at `s = −4/P_cr`.

The Ziegler–Nichols rules are explicitly described by their authors as targeting *quarter-amplitude damping*, i.e. a decay ratio of about 1/4 between successive overshoots. This corresponds to a closed-loop damping ratio of approximately `ζ ≈ 0.21`, which produces relatively oscillatory step responses (overshoots of 25%–60% are typical, as Ogata illustrates explicitly with overshoots of approximately 62% in Example 8-1, p. 574). The Ziegler–Nichols values are therefore best regarded as a *first guess* for subsequent fine tuning.

Original reference: J. G. Ziegler and N. B. Nichols, "Optimum Settings for Automatic Controllers," *Trans. ASME*, vol. 64, pp. 759–768, 1942.

### 6.3 Internal Model Control (IMC) tuning

IMC tuning, due principally to Morari, Rivera, and Skogestad, derives the PID parameters analytically from a model `G_p(s)` and a desired closed-loop time constant `λ`. The IMC controller is

```
Q(s) = G_p^{−1}(s) f(s),
```

where `f(s)` is a low-pass filter of the form

```
f(s) = 1 / (λ s + 1)^n,
```

and `n` is chosen large enough to make `Q(s)` proper. In the unity-feedback equivalent (Smith predictor structure), the IMC controller corresponds to a feedback controller

```
G_c(s) = Q(s) / [1 − G_p(s) Q(s)].
```

For the FOPDT plant `G_p(s) = K e^{−L s}/(T s + 1)`, after a first-order Padé approximation of the delay `e^{−L s} ≈ (1 − L s/2)/(1 + L s/2)`, the IMC controller is algebraically equivalent to a PID with parameters

```
K_p = (T + L/2) / [K (λ + L/2)],
T_i = T + L/2,
T_d = T L / (2 T + L).
```

The single tuning parameter `λ` directly trades off speed and robustness: smaller `λ` yields a faster response but smaller stability margins; larger `λ` produces a sluggish but more robust loop. For self-regulating processes, the IMC and *λ-tuning* rules coincide for PI controllers and produce a first-order setpoint response of the form `(1/(λ s + 1)) e^{−L s}`.

Original reference: D. E. Rivera, M. Morari, and S. Skogestad, "Internal Model Control. 4. PID Controller Design," *Industrial & Engineering Chemistry Process Design and Development*, vol. 25, no. 1, pp. 252–265, 1986.

### 6.4 Frequency-response tuning

Ogata, §8-3 presents a frequency-response design procedure in which the PID controller is decomposed as

```
G_c(s) = K (a s + 1)(b s + 1) / s,
```

i.e. as an integrator followed by two stable lead networks. Given specifications on the static velocity error constant `K_v`, phase margin `φ_m`, and gain margin `g_m`, the procedure is:

1. Solve `K_v = lim_{s→0} s G_c(s) G_p(s)` for the gain `K`.
2. Plot the Bode diagram of `K G_p(s)/s` and locate the gain crossover frequency `ω_g`.
3. Choose `a` so that the lead network `(a s + 1)` provides phase advance in a neighbourhood of `ω_g`.
4. Choose `b` to meet the phase margin requirement.

This yields a controller of the form

```
G_c(s) = K (a s + 1)(b s + 1) / s = K_p [1 + 1/(T_i s) + T_d s],
```

with

```
K_p = K (a + b),    T_i = a + b,    T_d = ab / (a + b),
```

which is again a PID controller in standard parametric form.

### 6.5 Computational optimisation

Ogata, §8-4 presents a computational tuning approach in which the parameter triple `(K, a, T)` of the controller `G_c(s) = K(s+a)²/s` (a special case of the PID with double zero) is searched on a discretised grid. The optimisation criterion is a transient-response specification, e.g. that the maximum overshoot `M_p` and settling time `t_s` of the closed-loop unit-step response satisfy

```
M_p ≤ M_p^{max},     t_s ≤ t_s^{max},
```

and the cost is evaluated by direct numerical simulation of the closed-loop. This approach is particularly natural in modern environments (e.g. MATLAB/Simulink) where the simulation cost is negligible compared with analytical effort.

---

## 7. Stability and Robustness

### 7.1 Routh–Hurwitz criterion

For a PID-controlled loop with rational `G_p(s)`, the closed-loop characteristic polynomial is a polynomial in `s` of degree `n + 1` (where `n` is the order of `G_p`). Stability is checked by the Routh–Hurwitz criterion: all entries in the first column of the Routh array must be strictly positive (Ogata, §5-6). The marginal stability gain `K_cr` of a P-controlled loop is the value of `K_p` for which a row of the Routh array vanishes; the corresponding oscillation frequency `ω_cr` is recovered from the auxiliary polynomial.

### 7.2 Phase and gain margins

The PID controller introduces both phase lag (from the integrator) and phase lead (from the derivative term). For a typical FOPDT plant, the maximum achievable phase margin under PID control is bounded by the structural constraint that the controller has at most two zeros, and so contributes at most 180° of phase lead minus 90° of phase lag, i.e. a net 90° at high frequency. This sets the practical limit on the achievable closed-loop bandwidth.

### 7.3 The role of the second derivative

The textbook PID controller uses only the first derivative of the error. Higher-order derivative actions (e.g. PIDD²) have been investigated in the literature, and may be analysed by the same techniques developed above; in practice their use is limited because the additional differentiator introduces severe noise amplification.

---

## 8. Summary of Closed-Loop Effects of the Three Actions

The qualitative effects of the proportional, integral, and derivative actions on the closed-loop behaviour are summarised in Table 2. Care should be taken in interpreting this table: the entries are *typical tendencies* and presuppose that the controller is being adjusted starting from a stabilising baseline.

| Action increased  | Rise time     | Overshoot  | Settling time | Steady-state error | Stability  |
| ----------------- | ------------- | ---------- | ------------- | ------------------ | ---------- |
| `K_p` ↑           | Decreases     | Increases  | Small effect  | Decreases          | Degrades   |
| `K_i` ↑ (`T_i` ↓) | Decreases     | Increases  | Increases     | Eliminates         | Degrades   |
| `K_d` ↑ (`T_d` ↑) | Small effect  | Decreases  | Decreases     | No direct effect   | Improves (within filter limits) |

The table is consistent with the analytical results of Sections 3–5: the proportional gain raises low-frequency gain (improving error and speed), the integral action eliminates the steady-state error but introduces phase lag, and the derivative action injects damping.

---

## 9. Worked Example: PID via Ziegler–Nichols (Second Method)

Consider the plant (Ogata, Example 8-1)

```
G_p(s) = 1 / [s (s + 1)(s + 5)].
```

### 9.1 Determination of `K_cr` and `P_cr`

With proportional control alone the characteristic polynomial is

```
s³ + 6 s² + 5 s + K_p = 0.
```

The Routh array is

```
s³ |   1     5
s² |   6     K_p
s¹ | (30 − K_p)/6
s⁰ |   K_p
```

The `s¹` row vanishes at `K_p = K_cr = 30`. Substituting `s = jω` into the characteristic polynomial at this gain yields `6(5 − ω²) + jω(5 − ω²) = 0`, so `ω_cr = √5` rad/s, and

```
P_cr = 2π / ω_cr = 2π / √5 ≈ 2.8099 s.
```

### 9.2 Application of the rule

By Table 8-2:

```
K_p = 0.6 · K_cr      = 18,
T_i = 0.5 · P_cr      = 1.405 s,
T_d = 0.125 · P_cr    = 0.35124 s.
```

The controller is

```
G_c(s) = 18 [1 + 1/(1.405 s) + 0.35124 s] = 6.3223 (s + 1.4235)² / s.
```

### 9.3 Closed-loop response

The closed-loop transfer function is

```
T(s) = (6.3223 s² + 18 s + 12.811) / (s⁴ + 6 s³ + 11.3223 s² + 18 s + 12.811).
```

Numerical simulation (Ogata, Fig. 8-8) yields a maximum overshoot of approximately 62%, well above typical performance specifications. Fine tuning, e.g. moving the double zero from `s = −1.4235` to `s = −0.65` while keeping `K_p = 18`, reduces the overshoot to about 18% (Ogata, Eq. 8-1). Increasing `K_p` to 39.42 with the relocated zero gives an overshoot of about 28% with a faster response (Ogata, Eq. 8-2). These observations confirm that the Ziegler–Nichols rules are best understood as providing initial parameter values for subsequent refinement.

---

## 10. Beyond the Classical PID: Modified Structures

Ogata, §§8-5 to 8-7 collects several *modified PID* schemes that exploit the algebraic freedom available once the controller is decomposed into feedforward and feedback branches.

### 10.1 PI-D and I-PD revisited

Both schemes were defined in Section 5.4 above. The disturbance response is identical to that of the textbook PID, but the reference-to-output transfer function differs:

```
Y(s)/R(s)|_PID  = (1 + 1/(T_i s) + T_d s) K_p G_p(s) / D̃(s),       (PID)
Y(s)/R(s)|_PI-D = (1 + 1/(T_i s)) K_p G_p(s) / D̃(s),               (PI-D)
Y(s)/R(s)|_I-PD = (1/(T_i s)) K_p G_p(s) / D̃(s),                  (I-PD)
```

with the common denominator

```
D̃(s) = 1 + K_p G_p(s) (1 + 1/(T_i s) + T_d s).
```

The pure proportional and derivative actions are progressively removed from the *direct* path as one passes from PID → PI-D → I-PD, which softens the response to setpoint changes without altering disturbance rejection. The I-PD structure requires an integral term to be present (otherwise the reference does not enter the loop at all).

### 10.2 Two-degrees-of-freedom (2-DOF) PID

The control system is *one degree of freedom* if and only if the closed-loop transfer functions `G_yr = Y/R`, `G_yd = Y/D`, and `G_yn = Y/N` (noise) satisfy

```
G_yn = − G_c G_p / (1 + G_c G_p),    G_yr = G_c G_p / (1 + G_c G_p),    G_yd = G_p / (1 + G_c G_p),
```

so that knowledge of one transfer function determines the other two. In a 2-DOF configuration with controllers `G_{c1}` (in the forward path) and `G_{c2}` (in the feedback path), one obtains

```
G_yr = G_{c1} G_p / [1 + (G_{c1} + G_{c2}) G_p],
G_yd = G_p     / [1 + (G_{c1} + G_{c2}) G_p],
G_yn = − (G_{c1} + G_{c2}) G_p / [1 + (G_{c1} + G_{c2}) G_p],
```

so that the reference response and the disturbance response can be shaped independently by the choice of `G_{c1}` and `G_{c2}`.

### 10.3 Zero-placement design

Ogata, §8-7 presents a zero-placement procedure for 2-DOF control. Given a stable target denominator polynomial of degree `n + 1`, the numerator zeros of `Y(s)/R(s)` are chosen so that the closed-loop transfer function has the form

```
Y(s)/R(s) = (a₂ s² + a₁ s + a₀) / (s^{n+1} + a_n s^n + ⋯ + a₂ s² + a₁ s + a₀),
```

i.e. the last three coefficients of the denominator coincide with the numerator coefficients. This algebraic condition is shown to be equivalent to *zero steady-state error against step, ramp, and acceleration references* simultaneously, while leaving sufficient freedom to also shape the disturbance response.

---

## 11. Discrete-Time Implementation

Modern PID controllers are almost always implemented in discrete time. The standard discretisations of the three actions, with sampling period `h`, are:

- **Proportional:** `u_P[k] = K_p e[k]`.
- **Integral:** by the trapezoidal (Tustin) rule,

  ```
  u_I[k] = u_I[k−1] + (K_p h / (2 T_i)) (e[k] + e[k−1]).
  ```

- **Derivative (filtered):** by backward differences applied to the filter `T_d s/(1 + (T_d/N) s)`,

  ```
  u_D[k] = (T_d / (T_d + N h)) u_D[k−1]
            + (K_p T_d N / (T_d + N h)) (y[k−1] − y[k]),
  ```

  noting that derivative-on-output (PI-D) is used to eliminate setpoint kicks.

The total control is `u[k] = u_P[k] + u_I[k] + u_D[k]`, optionally clipped by an actuator-saturation block followed by the back-calculation anti-windup feedback described in Section 5.6.

The Tustin discretisation of the integral term preserves stability of the open-loop integrator and is therefore preferable to Euler discretisation; for the derivative term, however, the backward-difference (Euler) scheme avoids the algebraic loop introduced by Tustin and is universally adopted in industrial PID blocks.

---

## 12. Conclusions and Outlook

The PD, PI, and PID controllers can be deduced from a small number of structural choices: which combinations of the proportional, integral, and derivative actions enter the forward and feedback paths, and in what order. The mathematical structure is invariant: a PID controller has exactly one pole at the origin and at most two zeros, and the corresponding closed-loop characteristic polynomial is of order `n_p + 1`, where `n_p` is the order of the plant.

The classical contributions can be summarised as follows. The Ziegler–Nichols rules of 1942 reduce the tuning problem to two model parameters (`K_cr`, `P_cr`) or (`L`, `T`) read directly from a closed-loop or open-loop experiment. The IMC framework of 1986 relates the PID parameters analytically to a single design knob `λ`, the desired closed-loop time constant. The frequency-response design procedure (Ogata, §8-3) produces a PID controller meeting prescribed velocity-error, phase-margin, and gain-margin specifications. The modified PID structures (PI-D, I-PD, 2-DOF) decouple the reference response from the disturbance response, and the zero-placement method of Ogata, §8-7 makes this decoupling rigorous.

Despite the development of many advanced control techniques (model predictive control, robust H∞ control, adaptive control, fuzzy and neural controllers), the textbook PID and its near relatives remain the dominant industrial paradigm. Ogata reports that more than half of all industrial controllers in service are PID or modified PID controllers (Ogata, p. 567); this estimate has been corroborated by surveys conducted independently by Åström and Hägglund (1995, 2001), and the figure has been stable across decades. The reasons are structural: the PID controller imposes minimal demands on the plant model, requires only three (or four, with a derivative filter) parameters, and admits direct interpretation in terms of phase lead, phase lag, and steady-state error.

---

## Sources

Primary textbook used:

- K. Ogata, *Modern Control Engineering*, 5th ed., Prentice Hall, 2010. Specifically Chapter 2 (§§2-3), Chapter 5 (§§5-7, 5-8), and Chapter 8 (§§8-1 to 8-7).

Primary research literature:

- J. G. Ziegler and N. B. Nichols, "Optimum Settings for Automatic Controllers," *Transactions of the ASME*, vol. 64, pp. 759–768, 1942. Available online at [skoge.folk.ntnu.no](https://skoge.folk.ntnu.no/puublications_others/1942_ziegler-nichols.pdf).
- D. E. Rivera, M. Morari, and S. Skogestad, "Internal Model Control. 4. PID Controller Design," *Industrial & Engineering Chemistry Process Design and Development*, vol. 25, no. 1, pp. 252–265, 1986. Available online at [skoge.folk.ntnu.no](https://skoge.folk.ntnu.no/publications/1986/Rivera86/Rivera86.pdf).
- K. J. Åström and T. Hägglund, *PID Controllers: Theory, Design, and Tuning*, 2nd ed., Instrument Society of America, 1995. Available at [ucg.ac.me](https://www.ucg.ac.me/skladiste/blog_2146/objava_92847/fajlovi/Astrom.pdf).
- K. J. Åström and T. Hägglund, "The Future of PID Control," *Control Engineering Practice*, vol. 9, no. 11, pp. 1163–1175, 2001.
- K. J. Åström and R. M. Murray, *Feedback Systems: An Introduction for Scientists and Engineers*, Princeton University Press, 2008, Chapter 10 ("PID Control"). Available at [cds.caltech.edu](https://www.cds.caltech.edu/~murray/books/AM08/pdf/am08-pid_04Mar10.pdf).

Supplementary references on practical implementation:

- "PID Controller — Anti-Windup Control," MathWorks Simulink documentation. Available at [mathworks.com](https://www.mathworks.com/help/simulink/slref/anti-windup-control-using-a-pid-controller.html).
- "Lambda Tuning — the Universal Method for PID Controllers in Process Control," Emerson Automation Solutions technical white paper. Available at [emerson.com](https://www.emerson.com/documents/automation/lambda-tuning-universal-method-for-pid-controllers-in-process-control-en-42704.pdf).
- "Proportional–Integral–Derivative Controller," *Wikipedia*. Available at [en.wikipedia.org](https://en.wikipedia.org/wiki/Proportional%E2%80%93integral%E2%80%93derivative_controller).
