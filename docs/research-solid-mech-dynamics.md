# Fuzzy Logic for Structural Vibration Control — Research Note

A scoping study of fuzzy-logic applications in solid-mechanics dynamics, with emphasis on **vibration control of structures**, intended to identify a tractable next exercise for this repository.

---

## 1. Why this domain fits fuzzy logic

Structural vibration control is a textbook application of fuzzy logic, and one of the earliest non-process-control domains to adopt it. Three properties of the problem make Mamdani-style controllers a natural choice:

1. **Nonlinear, time-varying plants.** Real structures exhibit hysteresis (especially with friction or magnetorheological dampers), gap nonlinearities (base isolation), and parametric uncertainty (mass and stiffness drift with temperature, payload, damage). Fuzzy controllers do not require a precise mathematical model — they rely on rule-based reasoning, which makes them particularly suitable for systems that are uncertain or nonlinear in nature.
2. **Expert knowledge is rule-shaped.** Civil and mechanical engineers describe control intuition linguistically: *"if the floor is moving fast and far, brake hard; if it has just reversed direction, ease off"*. This is exactly the form of a Mamdani rule base.
3. **Sensor data is noisy and partial.** Fuzzy controllers degrade gracefully under sensor noise and missing inputs; their interpolation across rules acts as implicit smoothing.

The field has been active since the early 1990s and remains so — recent (2024–2025) work focuses on Type-2 / Type-3 fuzzy controllers, ANFIS, and reinforcement-learned fuzzy policies for smart isolation systems and active piezoelectric actuators.

---

## 2. Application landscape

### 2.1 Tall buildings (wind and seismic)

- **Active / Active Tuned Mass Dampers (AMD / ATMD)** — secondary mass on top of a building, driven by an actuator commanded by the controller. Commercial deployments include Taipei 101, Citicorp Center.
- **Magnetorheological (MR) dampers** — semi-active devices whose damping coefficient is modulated by an applied magnetic field. Most-studied actuator in fuzzy-control literature: large force capacity, high dynamic range, low power requirement, fail-safe (acts as passive damper if power lost).
- **Base isolation systems** — soft layer between foundation and superstructure; fuzzy logic adjusts the damping of the isolation interface (often via an MR damper) to balance isolation vs. drift.

The classic benchmark in this category is the **76-story reinforced concrete office tower proposed for Melbourne, Australia**, used as a standard wind-excited test case for control algorithms.

### 2.2 Bridges

- **Cable-stayed bridges** — cables and deck both vibrate under wind and traffic. Semi-active MR dampers at cable anchorages, fuzzy-controlled, are a mature line of research.
- **Suspension bridges** — flutter suppression with active aerodynamic surfaces, fuzzy-tuned.

### 2.3 Smart beams, plates, and small-scale structures

- **Cantilever beams with piezoelectric (PZT) actuators** — the laboratory-scale workhorse. PZT senses deformation (charge from strain) and actuates (deforms under voltage). Fuzzy controllers map measured tip displacement / velocity to actuator voltage.
- **Plates and panels** — distributed PZT or macro-fiber-composite (MFC) actuators with multimode fuzzy controllers (ANFIS variants are common here).
- **Aerospace components** — flexible space structures, satellite booms, robotic arms.

### 2.4 Vehicles

- **Semi-active automotive suspensions** — MR dampers, fuzzy control for ride comfort vs. handling trade-offs.
- **Train pantograph / catenary** — pantograph contact-force regulation.

---

## 3. Actuator technologies (and how they shape the controller)

| Actuator | Type | Force range | Bandwidth | Fuzzy-control role |
|----------|------|-------------|-----------|---------------------|
| Active Mass Damper (AMD) | Active | 10² – 10⁵ N | low–medium | Output = command force |
| Magnetorheological (MR) damper | Semi-active | 10³ – 10⁵ N | high | Output = current/voltage to coil |
| Piezoelectric (PZT) stack | Active | 1 – 10² N | very high | Output = applied voltage |
| Hydraulic | Active | 10³ – 10⁶ N | medium | Output = command force |
| Electromagnetic | Active | 10² – 10⁴ N | medium-high | Output = command force |

**Active vs. semi-active matters for the control design:**

- *Active*: the controller can inject energy. Output = commanded force (can be any sign, any magnitude up to actuator limits).
- *Semi-active* (MR damper, variable orifice): the controller can only modulate dissipation. The output force always opposes velocity; what the controller chooses is the *magnitude*. This constrains the rule base — "Acelerar" is not an option, only "amortecer mais" or "amortecer menos".

---

## 4. Controller architectures

### 4.1 Mamdani

Most common. Three ingredients:

- **Inputs** (typically 2): displacement and velocity of a key DOF, or error and error-rate against a setpoint (often zero).
- **Rule base** (typically 3 × 3, 5 × 5, or 7 × 7).
- **Output** (typically 1): control force, voltage, or current.

A canonical 5 × 5 rule base for an active-force controller looks like:

|              | Disp NB | Disp NS | Disp Z  | Disp PS | Disp PB |
|--------------|---------|---------|---------|---------|---------|
| **Vel NB**   | PB      | PB      | PS      | Z       | NS      |
| **Vel NS**   | PB      | PS      | PS      | Z       | NS      |
| **Vel Z**    | PS      | PS      | Z       | NS      | NS      |
| **Vel PS**   | PS      | Z       | NS      | NS      | NB      |
| **Vel PB**   | PS      | Z       | NS      | NB      | NB      |

(NB = Negative Big, NS = Negative Small, Z = Zero, PS = Positive Small, PB = Positive Big.)

The rule base implements a phase-plane controller — diagonally symmetric — that opposes motion energetically. This is the fuzzy analogue of a PD controller.

### 4.2 Sugeno / TSK

Used when the consequents are best expressed as functions of the state — e.g., Sugeno consequents `f_i = a_i x + b_i ẋ + c_i` can encode a piecewise-linear control law that mimics LQR in different regions of the phase plane.

### 4.3 ANFIS (Adaptive Neuro-Fuzzy Inference System)

Heavily used to *learn* the rule base or membership-function parameters from data — typically simulated training trajectories or LQR solutions. The fuzzy structure provides interpretability; the gradient-based training provides adaptation. ANFIS variants dominate cable-stayed bridge and multimode-beam control papers.

### 4.4 Type-2 fuzzy

Models uncertainty in the membership functions themselves (e.g., expert disagreement on what counts as "Big"). More expensive but robust; popular in seismic-control papers where ground-motion characteristics are inherently uncertain.

### 4.5 Hybrid schemes

- **GA-fuzzy** — genetic algorithms tune MF parameters to minimize a cost (peak displacement, RMS acceleration).
- **Wavelet-fuzzy** — wavelet decomposition of the input signal feeds a fuzzy controller; popular for non-stationary excitations.
- **DRL-fuzzy** — deep reinforcement learning trains the rule base; recent (2024–2025) work for piezoelectric smart isolation systems.

---

## 5. Mathematical models

### 5.1 Single-degree-of-freedom (SDOF)

The cleanest pedagogical model: a single mass, spring, and damper, with an external force and a control force.

$$
m\,\ddot{x}(t) + c\,\dot{x}(t) + k\,x(t) = F_\text{ext}(t) + u(t)
$$

For base-excited problems (earthquake on a single floor), the equation becomes:

$$
m\,\ddot{x} + c\,\dot{x} + k\,x = -m\,\ddot{x}_g(t) + u(t)
$$

where $\ddot{x}_g$ is the ground acceleration and $x$ is the displacement *relative* to the ground.

The fuzzy controller maps $(x, \dot{x}) \mapsto u$.

### 5.2 SDOF with Tuned Mass Damper (2-DOF)

Adds an auxiliary mass $m_d$ on a spring $k_d$ and damper $c_d$ attached to the main mass:

$$
\begin{aligned}
m\,\ddot{x} + (c + c_d)\,\dot{x} - c_d\,\dot{x}_d + (k + k_d)\,x - k_d\,x_d &= F_\text{ext} + u_d \\
m_d\,\ddot{x}_d + c_d\,(\dot{x}_d - \dot{x}) + k_d\,(x_d - x) &= -u_d
\end{aligned}
$$

The control force $u_d$ acts on the damper mass. For *passive* TMDs, $u_d = 0$ and the damper is tuned to the structure's natural frequency. For *active* (ATMD) or *semi-active* (MR damper inside the TMD link), $u_d$ is fuzzy-commanded.

### 5.3 Multi-DOF (full building)

For an $n$-story shear-building model:

$$
\mathbf{M}\,\ddot{\mathbf{x}} + \mathbf{C}\,\dot{\mathbf{x}} + \mathbf{K}\,\mathbf{x} = -\mathbf{M}\,\mathbf{1}\,\ddot{x}_g + \mathbf{B}\,\mathbf{u}
$$

with $\mathbf{B}$ specifying which floor each actuator acts on. Most fuzzy controllers in the literature reduce this to a few measured inputs (typically top-floor displacement and velocity, or inter-story drift and drift-rate) before applying inference.

### 5.4 Cantilever beam with PZT

Reduce the Euler–Bernoulli PDE to its first one or two modes via Galerkin projection — each mode then behaves as an SDOF with effective mass, stiffness, and damping. The PZT actuator's bending-moment input couples in via a mode-shape integral. This collapses neatly into the SDOF model above for the dominant first mode.

---

## 6. Input/output design heuristics

### 6.1 Choice of inputs

- **Displacement and velocity** of a key DOF — most common, gives phase-plane control.
- **Error and error-rate** against a (usually zero) reference — equivalent for set-point regulation.
- **Acceleration** alone — used when only accelerometers are available and double-integration is unreliable.
- **Inter-story drift and drift-rate** — for multi-story buildings.

### 6.2 Universe-of-discourse scaling

The plant's natural amplitudes are highly problem-specific (mm for a beam tip, cm for a building floor, μm for a precision instrument). Standard practice: **normalize** the inputs by characteristic scales before fuzzification, and **denormalize** the output. This makes the rule base portable.

$$
\tilde{x} = \frac{x}{x_\text{ref}}, \quad \tilde{\dot{x}} = \frac{\dot{x}}{\dot{x}_\text{ref}}, \quad u = u_\text{ref}\,\tilde{u}
$$

The three scaling gains $(x_\text{ref}, \dot{x}_\text{ref}, u_\text{ref})$ become the *tunable* part of the controller — they trade response speed against control effort and are often optimized by GA.

### 6.3 Membership function design

- Triangular / trapezoidal MFs are standard for interpretability.
- Gaussian / bell MFs are preferred when the controller is to be tuned by gradient (ANFIS).
- 5 or 7 terms per input is the sweet spot — enough resolution to encode a phase-plane controller, few enough to keep the rule base manageable.

### 6.4 Output for semi-active devices

For MR dampers, the output is typically the commanded *current* or *voltage*, in [0, V_max]. The rule base then maps high $|x|$ and $|\dot{x}|$ → high voltage (more damping), and the device cannot push against velocity by physics.

---

## 7. Benchmark problems

The structural-control community maintains canonical benchmark problems with published baseline controllers. The most relevant for fuzzy-control research:

- **ASCE 76-story Melbourne benchmark** — wind-excited tall building with ATMD. Standard test for active control.
- **ASCE 3-, 9-, 20-story SAC buildings** — seismic-excited steel-moment-frame buildings. Standard test for semi-active control.
- **ASCE base-isolated benchmark** — base-isolated building with MR damper.
- **ASCE cable-stayed bridge benchmark** — long-span deck with semi-active dampers.

These benchmarks define a fixed plant model, ground motions or wind force histories, performance indices (peak displacement, RMS acceleration, control effort), and a passive-control baseline. They are excellent for *comparing* controller designs but are too large for a first exercise — each is a multi-DOF model with hundreds of states.

---

## 8. Recommended next exercise

Three options, ranked by tractability:

### Option A (recommended) — SDOF active vibration control under harmonic excitation

A single-DOF mass-spring-damper system excited by a harmonic force. Mamdani fuzzy controller with two inputs (displacement, velocity) and one output (active control force). 5 × 5 phase-plane rule base.

- **Plant:** $m\,\ddot{x} + c\,\dot{x} + k\,x = F_0\sin(\omega t) + u(t)$
- **Inputs:** $x \in [-x_\text{max}, +x_\text{max}]$, $\dot{x} \in [-\dot{x}_\text{max}, +\dot{x}_\text{max}]$
- **Output:** $u \in [-u_\text{max}, +u_\text{max}]$
- **Comparison:** uncontrolled response vs. fuzzy-controlled response, plus a passive-damper baseline.
- **Plots:** MFs (3), rule-base table, control surface (3D), time-domain $x(t)$ and $u(t)$ traces, frequency response.

This mirrors the motor-control exercise's structure (simple plant, two-input fuzzy controller, simulation plots) and demonstrates the *phase-plane* style rule base.

### Option B — SDOF + passive vs. active TMD

Add a tuned mass damper to the SDOF system. Compare three cases: no TMD, passive TMD (no control), active TMD with fuzzy controller.

- More mechanical realism; introduces 2-DOF dynamics.
- Reveals the TMD's natural-frequency tuning trade-offs.
- More plotting work; same fuzzy controller structure as Option A.

### Option C — base-excited SDOF under recorded earthquake

Replace harmonic excitation with a recorded ground-motion history (El Centro 1940, Kobe 1995). Same fuzzy controller as Option A; demonstrates real-world seismic protection performance.

- More realistic but requires loading a numpy time series of ground acceleration.
- Use it as a *follow-up* once Option A is in place.

**Suggestion:** start with Option A. Once it's working, Option C is a natural extension that reuses the same FIS and only swaps the excitation.

---

## 9. Implementation notes for this repo

The `fuzzy/` package already supports everything Option A needs:

- `fuzzy.membership` — triangular and trapezoidal MFs (sufficient for 5 NB/NS/Z/PS/PB terms).
- `fuzzy.fis.MamdaniFIS` — handles the 5 × 5 rule base out of the box.
- `fuzzy.defuzz.centroid` — standard defuzzification.

What needs to be added:

- A small SDOF integrator. Either an explicit RK4 wrapper over `dxdt = f(x, t, u)`, or a one-shot `scipy.integrate.solve_ivp` call. RK4 is more transparent and only ~10 lines.
- Frequency-response sweep (plot $|x|$ vs. $\omega$ for controlled and uncontrolled cases).
- Optional: GA tuning of the input scaling gains using `scipy.optimize.differential_evolution`.

No new fuzzy-side library code is required; the exercise is mostly the plant + driver code under `exercises/exercicio2_<name>/`.

---

## 10. References

### Recent reviews and surveys

- Mahmoud et al., *Deep online learning type-3 fuzzy structural control strategy for active vibration suppression: real-world validation*, **International Journal of Dynamics and Control** (2025). [link](https://link.springer.com/article/10.1007/s40435-025-01910-4)
- *State-of-the-Art Review of Structural Vibration Control: Overview and Research Gaps*, **Applied Sciences** (MDPI), 15(14), 7966 (2025). [link](https://www.mdpi.com/2076-3417/15/14/7966)
- *A Critical Review on Control Strategies for Structural Vibration Control*, **Annual Reviews in Control** (2022). [link](https://www.sciencedirect.com/science/article/abs/pii/S1367578822000979)
- *Artificial Intelligence for Structural Vibration Control: A Review of Previous Studies and Methodologies*, **Springer** (2024). [link](https://link.springer.com/chapter/10.1007/978-3-032-07738-7_9)

### MR dampers and fuzzy semi-active control

- *Review of Magnetorheological Damping Systems on a Seismic Building*, **Applied Sciences** (MDPI), 11(19), 9339 (2021). [link](https://www.mdpi.com/2076-3417/11/19/9339)
- Bozorgvar & Zahrai, *Semi-active seismic control of buildings using MR damper and adaptive neural-fuzzy intelligent controller optimized with genetic algorithm*, **Journal of Vibration and Control** (2019). [link](https://doi.org/10.1177/1077546318774502)
- *A comparative evaluation of semi-active control algorithms for real-time seismic protection of buildings via magnetorheological fluid dampers*, **Structures** (2021). [link](https://www.sciencedirect.com/science/article/abs/pii/S2352710221006537)
- *A semi-active control system in coupled buildings with base-isolation and magnetorheological dampers using an adaptive neuro-fuzzy inference system*, **Frontiers in Built Environment** (2022). [link](https://www.frontiersin.org/journals/built-environment/articles/10.3389/fbuil.2022.1057962/full)
- *Integrated fuzzy logic and genetic algorithms for multi-objective control of structures using MR dampers*, **Journal of Sound and Vibration** (2007). [link](https://www.sciencedirect.com/science/article/abs/pii/S0022460X06002173)

### Piezoelectric active vibration control

- Chu, Lin & Li, *Active multimode vibration control of a smart structure using macro fiber composite actuators based on ANFIS*, **Journal of Low Frequency Noise, Vibration and Active Control** (2020). [link](https://journals.sagepub.com/doi/10.1177/1461348419872305)
- Cui et al., *Active vibration optimal control of piezoelectric cantilever beam with uncertainties*, **Measurement and Control** (2022). [link](https://journals.sagepub.com/doi/10.1177/00202940221091244)
- *FUZZY-LOGIC BASED VIBRATION SUPPRESSION CONTROL EXPERIMENTS ON ACTIVE STRUCTURES*, **Journal of Sound and Vibration** (1996). [link](https://www.sciencedirect.com/science/article/abs/pii/S0022460X96901042)

### Benchmark problems

- *Fuzzy controller for seismically excited nonlinear buildings* (3-, 9-, 20-story SAC benchmarks). [link](https://www.academia.edu/1201174/Fuzzy_controller_for_seismically_excited_nonlinear_buildings)
- *Wavelet-neuro-fuzzy control of hybrid building-active tuned mass damper system under seismic excitations* (76-story benchmark). [link](https://www.academia.edu/32377300/Wavelet_neuro_fuzzy_control_of_hybrid_building_active_tuned_mass_damper_system_under_seismic_excitations)
- *GA-fuzzy control of smart base isolated benchmark building using supervisory control technique*, **Engineering Applications of Artificial Intelligence** (2007). [link](https://www.sciencedirect.com/science/article/abs/pii/S0965997806001682)
- *Tuning the Type-2 Fuzzy Controller for Active Control of Buildings Under Seismic Vibrations*, **Iranian Journal of Science and Technology, Transactions of Civil Engineering** (2022). [link](https://link.springer.com/article/10.1007/s40996-022-01001-w)
- SSTL Structural Control Benchmarks, University of Illinois Urbana-Champaign. [link](http://sstl.cee.illinois.edu/benchmarks/)
- *Fuzzy logic based adaptive vibration control system for structures subjected to seismic and wind loads*, **Structures** (2023). [link](https://www.sciencedirect.com/science/article/pii/S2352012423008688)
