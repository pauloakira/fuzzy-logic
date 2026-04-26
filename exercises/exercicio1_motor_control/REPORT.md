# Report — DC motor speed control with predictive fuzzy logic

**PCS5708 — Exercise 1 — Mamdani approach**

## 1. Problem specification

Design a rotational speed control system for a DC motor using predictive fuzzy logic. Constraints:

- Motor: $\omega \in [0, 1000]$ rpm
- DC source: $V \in [0, 100]$ V
- Maximum acceleration / braking rate: $\pm 1$ rpm/s
- Control action: increment or decrement the supply voltage by $\pm 1$ V

Basic physical relationship: to accelerate the motor, raise the voltage; to brake, lower it. This heuristic is encoded in the rule base.

## 2. Variables and dimensioning

| Type   | Variable     | Domain         | Linguistic terms          |
| ------ | ------------ | -------------- | ------------------------- |
| Input  | Velocidade   | [0, 1000] rpm  | Baixa, Média, Alta        |
| Input  | Alimentação  | [0, 100] V     | Baixa, Média, Alta        |
| Output | Aceleração   | [-1, +1] rpm/s | Freio, Neutro, Aceleração |

The *control variable* — the relationship between acceleration (output) and supply voltage — is interpreted as follows: the fuzzy acceleration output (in rpm/s) is also the rate of change of the supply voltage (V/s). At a full *Acelerar* decision (output = +1), the source rises 1 V/s and the motor responds by accelerating at 1 rpm/s.

Linguistic-term glossary: Baixa = Low, Média = Medium, Alta = High; Freio = Brake, Neutro = Neutral, Aceleração = Accelerate.

## 3. Membership functions

The three variables use linear triangulars and shoulders, following the course slides.

### 3.1 Velocidade

- **Baixa**: descending shoulder — $\mu = 1$ at $\omega = 0$, $\mu = 0$ at $\omega = 500$.
- **Média**: triangular, peak at $\omega = 500$, base at $0$ and $1000$.
- **Alta**: rising shoulder — $\mu = 0$ at $\omega = 500$, $\mu = 1$ at $\omega = 1000$.

![Velocidade](figures/mf_velocidade.png)

### 3.2 Alimentação

Analogous, mapped to the interval $[0, 100]$ V.

![Alimentação](figures/mf_alimentacao.png)

### 3.3 Aceleração (output)

- **Freio**: descending shoulder — $\mu = 1$ at $-1$ rpm/s, $\mu = 0$ at $0$.
- **Neutro**: triangular, peak at $0$, base at $-1$ and $+1$.
- **Aceleração**: rising shoulder — $\mu = 0$ at $0$, $\mu = 1$ at $+1$ rpm/s.

![Aceleração](figures/mf_aceleracao.png)

## 4. Rule base

Nine rules (3 × 3) covering all combinations of the two input terms:

| Velocidade \ Alimentação | Baixa      | Média      | Alta      |
| ------------------------ | ---------- | ---------- | --------- |
| **Baixa**                | Aceleração | Aceleração | Neutro    |
| **Média**                | Aceleração | Neutro     | Freio     |
| **Alta**                 | Neutro     | Freio      | Freio     |

The base encodes a *predictive* heuristic:

- **Velocidade Baixa & Alimentação Baixa → Acelerar**: motor stopped, voltage low — raise voltage.
- **Velocidade Baixa & Alimentação Alta → Neutro**: motor slow but voltage high — the motor is about to accelerate from the voltage alone; do not push more.
- **Velocidade Alta & Alimentação Baixa → Neutro**: motor fast but voltage low — the motor will already decelerate; do not lower the voltage further.
- **Velocidade Alta & Alimentação Alta → Frear**: motor too fast and voltage high — reduce.

The *predictive* character lies in the anti-diagonal cells (Baixa × Alta and Alta × Baixa): instead of reacting only to the current state, the controller anticipates that the natural dynamics of the motor are already correcting it.

## 5. Inference

Classical Mamdani:

- t-norm for AND (between antecedents): `min`.
- Mamdani implication: clipping of the consequent membership function by the rule strength.
- Inter-rule aggregation: `max`.
- Defuzzification: centroid.

For each rule $i$:

$$
w_i = \min_{v \in \mathrm{antec}_i} \mu_{A_v}(x_v),
\qquad
\mu_{B_i'}(y) = \min(w_i,\ \mu_{B_i}(y))
$$

Aggregated output:

$$
\mu_{B'}(y) = \max_i \mu_{B_i'}(y)
$$

Crisp output by centroid:

$$
y^* = \frac{\sum_y y \cdot \mu_{B'}(y)}{\sum_y \mu_{B'}(y)}
$$

Defuzzification uses a discrete grid of 401 points over $[-1, +1]$.

## 6. Control surface

Evaluating the FIS over the full grid $[0, 1000] \times [0, 100]$:

![Control surface](figures/control_surface.png)

Observations:

- **Diagonal $\omega \approx 10 V$**: acceleration close to zero — implicit equilibrium.
- **"$\omega$ low, $V$ low" quadrant**: positive acceleration (accelerate).
- **"$\omega$ high, $V$ high" quadrant**: negative acceleration (brake).
- The surface is *smooth* (no discontinuities) thanks to the linguistic-term overlap and the centroid defuzzification.

## 7. Pointwise evaluations

Controller output at representative points:

| Velocidade (rpm) | Alimentação (V) | Aceleração (rpm/s) |
| ---------------: | --------------: | -----------------: |
|                0 |               0 |             +0.668 |
|              200 |              20 |             +0.177 |
|              500 |              50 |             +0.000 |
|              700 |              70 |             -0.076 |
|              900 |              90 |             -0.347 |
|             1000 |             100 |             -0.668 |

The symmetry around $(500, 50)$ reflects the symmetry of the rule base.

## 8. Plant model

Simplified DC motor model used for the simulation:

- Steady-state velocity: $\omega_{ss}(V) = 10\,V$.
- Natural response: $\dot\omega = \mathrm{clip}(\omega_{ss}(V) - \omega,\, -1,\, +1)$ rpm/s.
- Actuator: $\dot V = \mathrm{acc}_{\mathrm{FIS}}(\omega, V)$ V/s, saturated at $[0, 100]$ V.

The plant's max acceleration ($1$ rpm/s) is the main bottleneck — to traverse half its range ($500$ rpm), at least $500$ s are required.

## 9. Closed-loop simulation

Two initial conditions were simulated for $800$ s:

1. Motor at rest: $\omega(0) = 0$, $V(0) = 0$.
2. Motor saturated: $\omega(0) = 1000$, $V(0) = 100$.

![Simulation](figures/simulation.png)

Observations:

- Both trajectories converge to the neighborhood of the equilibrium $(\omega \approx 500\ \mathrm{rpm},\ V \approx 50\ \mathrm{V})$ — the state where only the rule (Média, Média $\to$ Neutro) fires at full strength and the controller output is zero.
- A small *overshoot* (~$\pm 100$ rpm) appears because of the rate-limited plant: the velocity cannot follow voltage changes immediately, and the voltage must "lead" before the plant responds.
- The commanded acceleration is monotonically decreasing in magnitude — typical of a smooth, stabilizing control surface.

## 10. Conclusions

- The fuzzy controller designed is **stable**: regardless of the initial condition within the operating space, the system converges to the equilibrium $(500, 50)$.
- The *prediction* built into the anti-diagonal rules (Baixa × Alta and Alta × Baixa, both mapping to *Neutro*) prevents excessive corrections, smoothing the response.
- Since the FIS receives only $(\omega, V)$ and no explicit *setpoint*, this controller, in its current form, regulates the motor at an implicit "middle" regime determined by the rule base. To *track* an arbitrary reference, the inputs would need to be transformed — e.g. use error $e = \omega_{\mathrm{ref}} - \omega$ and error rate $\dot e$ as inputs — preserving the same inference structure.
- The Mamdani method delivers a smooth and interpretable control surface: each quadrant is clearly associated with a linguistic decision, and tuning becomes a matter of adjusting the rule base or the membership functions, both transparent steps for a domain expert.

## 11. How to run

From the repository root:

```bash
python exercises/exercicio1_motor_control/motor_control.py
```

The run generates the five figures in `figures/` and prints the pointwise evaluation table to the terminal.
