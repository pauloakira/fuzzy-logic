"""Classical PID vs. Mamdani fuzzy — side-by-side comparison.

Reuses the SDOF plant, harmonic excitation, actuator limit, integration step,
metric window, and block diagram from `sdof_vibration.py`, so the only thing
that differs between the two controllers is the control law itself.

PID design
----------
Parallel-form PID with derivative-on-output and back-calculation
anti-windup (`fuzzy.blocks.PIDBlock`):

    u(t) = K_p · e(t)  +  K_i · ∫ e(τ) dτ  −  K_d · ẋ(t)

with e(t) = r(t) − x(t) and r ≡ 0 (regulation to zero displacement).
Derivative-on-output eliminates the setpoint kick and is equivalent to
derivative-on-error for constant r. See Ogata §8-5 and Åström & Hägglund
(1995).

Gains were chosen by pole-placement reasoning on the closed-loop
characteristic polynomial m·s² + (c + K_d)·s + (k + K_p) = 0:

- K_d = 10 boosts the damping ratio from ζ = 0.02 to ζ ≈ 0.46.
- K_p = 30 raises the effective stiffness modestly (shifts the resonance
  from 10 to ~11.4 rad/s), so the plant is no longer at resonance under
  the original 10 rad/s harmonic excitation.
- K_i = 5 is small (the forcing is zero-mean, so integral action has
  little to compensate for) but keeps the controller a true PID.

Fuzzy scaling gains
-------------------
The fuzzy controller's input scaling gain is swept as well. A gain of 1 is the
as-published controller; higher gains are equivalent to tighter universes of
discourse and are the fuzzy analogue of raising a state-feedback vector K. This
tests whether the fuzzy/PID gap is structural or merely a matter of tuning.

Outputs
-------
- figures/pid_simulation.png        — PID time-domain response at resonance
- figures/comparison_simulation.png — open / fuzzy / PID time-domain (overlaid)
- figures/comparison_frequency.png  — open / fuzzy / PID frequency response
- figures/gain_sweep.png            — fuzzy performance vs. input scaling gain
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from sdof_vibration import (
    DT,
    METRIC_WINDOW,
    OMEGA_N,
    T_MAX,
    U_MAX,
    ZETA,
    C,
    K,
    M,
    fuzzy_controller,
    response_metrics,
    run,
)

from fuzzy.blocks import PIDBlock

PID_PORTS = ("x", "x_dot")
PID_GAINS = {"kp": 30.0, "ki": 5.0, "kd": 10.0}
GAIN_SWEEP = [1.0, 2.0, 4.0, 7.0, 10.0]


def pid_controller(name: str = "controller") -> PIDBlock:
    """PID as a sampled block, sharing the actuator limit with the fuzzy case."""
    return PIDBlock(
        **PID_GAINS, lo=-U_MAX, hi=U_MAX, Tt=1.0, dt=DT, name=name
    )


def run_pid(omega: float = OMEGA_N, t_max: float = T_MAX):
    return run(pid_controller(), ports=PID_PORTS, omega=omega, t_max=t_max)


# ----- Plotting -------------------------------------------------------------


def plot_pid_simulation(figdir: Path) -> dict[str, float]:
    open_log = run(None)
    pid_log = run_pid()

    fig, axes = plt.subplots(3, 1, figsize=(10.0, 7.4), sharex=True)

    axes[0].plot(open_log.t, open_log.col("plant.y", 0), color="#d62728", lw=1.0,
                 label="Open loop", alpha=0.8)
    axes[0].plot(pid_log.t, pid_log.col("plant.y", 0), color="#2ca02c", lw=1.0,
                 label="PID")
    axes[0].set_ylabel("Displacement x (m)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(open_log.t, open_log.col("plant.y", 1), color="#d62728", lw=1.0,
                 alpha=0.8)
    axes[1].plot(pid_log.t, pid_log.col("plant.y", 1), color="#2ca02c", lw=1.0)
    axes[1].set_ylabel(r"Velocity $\dot x$ (m/s)")
    axes[1].grid(alpha=0.3)

    axes[2].plot(pid_log.t, pid_log["force.y"], color="gray", lw=0.8,
                 label=r"$F_{ext}(t)$", alpha=0.6)
    axes[2].plot(pid_log.t, pid_log["actuator.y"], color="#2ca02c", lw=1.0,
                 label="u(t) (PID)")
    axes[2].set_ylabel("Force (N)")
    axes[2].set_xlabel("Time (s)")
    axes[2].axvspan(T_MAX - METRIC_WINDOW, T_MAX, color="black", alpha=0.06,
                    label="steady-state window")
    axes[2].legend(loc="upper right", ncol=3, fontsize=9)
    axes[2].grid(alpha=0.3)

    fig.suptitle(
        r"PID — harmonic excitation at resonance "
        rf"($\omega = \omega_n = {OMEGA_N:.1f}$ rad/s)"
    )
    fig.tight_layout()
    fig.savefig(figdir / "pid_simulation.png", dpi=140)
    plt.close(fig)
    return response_metrics(pid_log)


def plot_comparison(figdir: Path) -> dict[str, dict[str, float]]:
    open_log = run(None)
    fuzzy_log = run(fuzzy_controller())
    pid_log = run_pid()

    fig, axes = plt.subplots(2, 1, figsize=(10.0, 6.8), sharex=True)

    axes[0].plot(open_log.t, open_log.col("plant.y", 0), color="#d62728", lw=0.9,
                 label="Open loop", alpha=0.7)
    axes[0].plot(fuzzy_log.t, fuzzy_log.col("plant.y", 0), color="#1f77b4", lw=1.0,
                 label="Fuzzy")
    axes[0].plot(pid_log.t, pid_log.col("plant.y", 0), color="#2ca02c", lw=1.0,
                 label="PID")
    axes[0].set_ylabel("Displacement x (m)")
    axes[0].legend(loc="upper right", ncol=3)
    axes[0].grid(alpha=0.3)

    axes[1].plot(fuzzy_log.t, fuzzy_log["actuator.y"], color="#1f77b4", lw=1.0,
                 label="Fuzzy")
    axes[1].plot(pid_log.t, pid_log["actuator.y"], color="#2ca02c", lw=1.0,
                 label="PID")
    axes[1].axhline(U_MAX, color="gray", linestyle=":", alpha=0.5,
                    label=r"$\pm U_{\max}$")
    axes[1].axhline(-U_MAX, color="gray", linestyle=":", alpha=0.5)
    axes[1].set_ylabel("Control force u (N)")
    axes[1].set_xlabel("Time (s)")
    axes[1].legend(loc="upper right", ncol=3)
    axes[1].grid(alpha=0.3)

    fig.suptitle("Fuzzy vs. PID — comparison at resonance")
    fig.tight_layout()
    fig.savefig(figdir / "comparison_simulation.png", dpi=140)
    plt.close(fig)

    return {
        "open": response_metrics(open_log),
        "fuzzy": response_metrics(fuzzy_log),
        "pid": response_metrics(pid_log),
    }


def plot_comparison_frequency(figdir: Path) -> None:
    omegas = np.linspace(0.4 * OMEGA_N, 1.8 * OMEGA_N, 18)
    amp = {"open": [], "fuzzy": [], "pid": []}

    for om in omegas:
        amp["open"].append(response_metrics(run(None, omega=om))["peak"])
        amp["fuzzy"].append(
            response_metrics(run(fuzzy_controller(), omega=om))["peak"]
        )
        amp["pid"].append(response_metrics(run_pid(omega=om))["peak"])

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    for key, label, color in (
        ("open", "Open loop", "#d62728"),
        ("fuzzy", "Fuzzy", "#1f77b4"),
        ("pid", "PID", "#2ca02c"),
    ):
        ax.plot(omegas / OMEGA_N, amp[key], color=color, marker="o",
                lw=1.8, markersize=5, label=label)
    ax.axvline(1.0, color="gray", linestyle=":", alpha=0.6, label=r"$\omega_n$")
    ax.set_xlabel(r"$\omega/\omega_n$")
    ax.set_ylabel("Steady-state amplitude (m)")
    ax.set_title("Frequency response — open loop vs. Fuzzy vs. PID")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figdir / "comparison_frequency.png", dpi=140)
    plt.close(fig)


def plot_gain_sweep(figdir: Path, pid_metrics: dict[str, float]) -> list[dict]:
    """Fuzzy peak amplitude and control effort against input scaling gain."""
    rows = []
    for g in GAIN_SWEEP:
        m = response_metrics(run(fuzzy_controller(gain=g)))
        rows.append({"gain": g, **m})

    gains = [r["gain"] for r in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.0))

    axes[0].plot(gains, [r["peak"] for r in rows], color="#1f77b4",
                 marker="o", lw=1.8, label="Fuzzy")
    axes[0].axhline(pid_metrics["peak"], color="#2ca02c", linestyle="--",
                    lw=1.5, label="PID")
    axes[0].set_xlabel("Input scaling gain")
    axes[0].set_ylabel("Peak |x| (m)")
    axes[0].set_title("Amplitude vs. scaling gain")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(gains, [r["u_peak"] for r in rows], color="#1f77b4",
                 marker="o", lw=1.8, label="Fuzzy")
    axes[1].axhline(pid_metrics["u_peak"], color="#2ca02c", linestyle="--",
                    lw=1.5, label="PID")
    axes[1].axhline(U_MAX, color="gray", linestyle=":", alpha=0.6,
                    label=r"$U_{\max}$")
    axes[1].set_xlabel("Input scaling gain")
    axes[1].set_ylabel("Peak |u| (N)")
    axes[1].set_title("Control effort vs. scaling gain")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.suptitle("Fuzzy controller — effect of input scaling gain")
    fig.tight_layout()
    fig.savefig(figdir / "gain_sweep.png", dpi=140)
    plt.close(fig)
    return rows


# ----- Entry point ----------------------------------------------------------


def main() -> None:
    figdir = Path(__file__).parent / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    pid_metrics = plot_pid_simulation(figdir)
    metrics = plot_comparison(figdir)
    plot_comparison_frequency(figdir)
    sweep = plot_gain_sweep(figdir, pid_metrics)

    o, f, p = metrics["open"], metrics["fuzzy"], metrics["pid"]
    zeta_pid = (C + PID_GAINS["kd"]) / (2.0 * np.sqrt((K + PID_GAINS["kp"]) * M))

    print(f"Plant: m={M:g} kg, k={K:g} N/m, zeta={ZETA}, omega_n={OMEGA_N:g} rad/s")
    print(f"PID gains: K_p={PID_GAINS['kp']:g}, K_i={PID_GAINS['ki']:g}, "
          f"K_d={PID_GAINS['kd']:g}  ->  closed-loop zeta={zeta_pid:.3f}")
    print(f"Horizon: t_max={T_MAX:g} s, metrics over the last {METRIC_WINDOW:g} s")
    print()
    print(f"Steady-state metrics at resonance (last {METRIC_WINDOW:g} s):")
    print(f"  Open loop:  peak={o['peak']:.4f} m,  rms={o['rms']:.4f} m")
    print(f"  Fuzzy:      peak={f['peak']:.4f} m,  rms={f['rms']:.4f} m,  "
          f"peak |u|={f['u_peak']:.3f} N")
    print(f"  PID:        peak={p['peak']:.4f} m,  rms={p['rms']:.4f} m,  "
          f"peak |u|={p['u_peak']:.3f} N")
    print()
    print("Reduction vs. open loop:")
    print(f"  Fuzzy:  {100 * (1 - f['peak'] / o['peak']):.1f}% peak,  "
          f"{100 * (1 - f['rms'] / o['rms']):.1f}% RMS")
    print(f"  PID:    {100 * (1 - p['peak'] / o['peak']):.1f}% peak,  "
          f"{100 * (1 - p['rms'] / o['rms']):.1f}% RMS")
    print()
    print("Fuzzy input scaling gain sweep (PID shown for reference):")
    for r in sweep:
        print(f"  gain={r['gain']:5.1f}  peak={r['peak']:.4f} m  "
              f"rms={r['rms']:.4f} m  peak |u|={r['u_peak']:.3f} N")
    print(f"  {'PID':>10}  peak={p['peak']:.4f} m  rms={p['rms']:.4f} m  "
          f"peak |u|={p['u_peak']:.3f} N")
    print()
    print(f"Figures saved to: {figdir}")


if __name__ == "__main__":
    main()
