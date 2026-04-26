# Exercício 2 — Controle ativo de vibrações em estrutura SDOF

Mamdani fuzzy controller for active vibration suppression of a single-degree-of-freedom (SDOF) mass-spring-damper structure under harmonic excitation.

## Specification

- Plant: SDOF mass-spring-damper, $m\ddot{x} + c\dot{x} + kx = F_\text{ext}(t) + u(t)$
- $m = 1$ kg, $k = 100$ N/m, damping ratio $\zeta = 0.02$ → natural frequency $\omega_n = 10$ rad/s
- Excitation: harmonic, $F_\text{ext}(t) = F_0 \sin(\omega t)$ with $F_0 = 1$ N
- Control: active force $u(t) \in [-3, +3]$ N from a Mamdani FIS

Inputs to the FIS: `deslocamento` ∈ [-0.3, +0.3] m, `velocidade` ∈ [-3, +3] m/s. Output: `forca` ∈ [-3, +3] N. Five linguistic terms each (NG, NP, Z, PP, PG); 5 × 5 phase-plane rule base.

## Files

- `sdof_vibration.py` — full solution: Mamdani FIS, RK4 SDOF integrator, simulation, plots.
- `REPORT.md` — full writeup. The four required deliverables (input variables, output variables, rules, application example) are each their own labeled section.
- `figures/` — generated PNGs.

## Running

From the repository root:

```bash
python exercises/exercicio2_sdof_vibration_control/sdof_vibration.py
```

Generates seven figures and prints summary metrics on the controlled vs. uncontrolled response.
