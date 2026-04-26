# Exercício 1 — Controle de velocidade de motor DC

Predictive fuzzy logic controller (Mamdani approach) for a DC motor.

## Specification

- Motor speed: ω ∈ [0, 1000] rpm
- Power supply voltage: V ∈ [0, 100] V
- Maximum (de)acceleration: ±1 rpm/s
- Voltage actuation rate: ±1 V/s

Inputs to the FIS: `velocidade`, `alimentacao`. Output: `aceleracao` ∈ [-1, +1] rpm/s.

## Files

- `motor_control.py` — full solution: Mamdani FIS, plant model, closed-loop simulation, plots.
- `REPORT.md` — full writeup (math, rule base, results, conclusions).
- `figures/` — generated PNGs.

## Running

From the repository root:

```bash
python exercises/exercicio1_motor_control/motor_control.py
```

Generates five figures in `figures/` and prints a small evaluation table.
