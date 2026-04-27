"""Classical PID vs. Mamdani fuzzy — side-by-side comparison.

Reuses the SDOF mass-spring-damper plant and harmonic excitation from
`sdof_vibration.py`, runs both controllers under identical conditions,
and produces comparison plots.

PID design
----------
Parallel-form PID with derivative-on-output and back-calculation
anti-windup:

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

Outputs
-------
- figures/pid_simulation.png        — PID time-domain response at resonance
- figures/comparison_simulation.png — open / fuzzy / PID time-domain (overlaid)
- figures/comparison_frequency.png  — open / fuzzy / PID frequency response
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Ensure repo root is on sys.path so `fuzzy.*` resolves; also allow
# importing the sibling `sdof_vibration` module from this directory.
sys.path.insert(0, str(Path(__file__).parent))

from sdof_vibration import (  # noqa: E402
    C,
    F0,
    K,
    M,
    OMEGA_N,
    U_MAX,
    build_fis,
    simulate,
)


# ----- PID controller -------------------------------------------------------


@dataclass
class PID:
    """Discrete PID with derivative-on-output and back-calculation anti-windup.

    Convention: regulation to setpoint = 0. Error e = setpoint - x = -x.
    With constant setpoint, derivative-on-output is equivalent to
    derivative-on-error: u_d = K_d · de/dt = -K_d · x_dot.

    The integrator is back-calculated when the actuator saturates, with
    time constant T_t (Åström & Hägglund 1995, §3.5).
    """

    K_p: float
    K_i: float
    K_d: float
    setpoint: float = 0.0
    u_min: float = -U_MAX
    u_max: float = U_MAX
    T_t: float = 1.0
    _I: float = field(default=0.0, init=False, repr=False)

    def reset(self) -> None:
        self._I = 0.0

    def step(self, x: float, x_dot: float, dt: float) -> float:
        e = self.setpoint - x
        u_p = self.K_p * e
        u_d = -self.K_d * x_dot
        u_unsat = u_p + self._I + u_d
        u_sat = float(np.clip(u_unsat, self.u_min, self.u_max))
        # Back-calculation: integrator state pulled toward saturation when active.
        self._I += dt * (self.K_i * e + (u_sat - u_unsat) / self.T_t)
        return u_sat


PID_GAINS = dict(K_p=30.0, K_i=5.0, K_d=10.0)


# ----- PID simulation -------------------------------------------------------


def _harmonic(t: float, omega: float) -> float:
    return F0 * np.sin(omega * t)


def _deriv(state: np.ndarray, t: float, omega: float, u: float) -> np.ndarray:
    x, v = state
    F = _harmonic(t, omega)
    return np.array([v, (F + u - C * v - K * x) / M])


def simulate_pid(
    pid: PID,
    omega: float,
    t_max: float,
    dt: float,
    x0: float = 0.0,
    v0: float = 0.0,
) -> dict[str, np.ndarray]:
    """RK4 simulation with PID feedback, zero-order hold on u."""
    n_steps = int(t_max / dt) + 1
    t = np.zeros(n_steps)
    x = np.zeros(n_steps)
    v = np.zeros(n_steps)
    u = np.zeros(n_steps)
    state = np.array([x0, v0])
    pid.reset()

    for i in range(n_steps - 1):
        u_now = pid.step(float(state[0]), float(state[1]), dt)
        u[i] = u_now

        k1 = _deriv(state, t[i], omega, u_now)
        k2 = _deriv(state + 0.5 * dt * k1, t[i] + 0.5 * dt, omega, u_now)
        k3 = _deriv(state + 0.5 * dt * k2, t[i] + 0.5 * dt, omega, u_now)
        k4 = _deriv(state + dt * k3, t[i] + dt, omega, u_now)
        state = state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        x[i + 1] = state[0]
        v[i + 1] = state[1]
        t[i + 1] = t[i] + dt

    u[-1] = pid.step(float(state[0]), float(state[1]), dt)
    return {"t": t, "x": x, "v": v, "u": u}


# ----- Plotting -------------------------------------------------------------


def plot_pid_simulation(pid: PID, figdir: Path) -> dict[str, float]:
    omega = OMEGA_N
    t_max = 12.0
    dt = 0.005

    h_open = simulate(omega, t_max=t_max, dt=dt, fis=None)
    h_pid = simulate_pid(pid, omega, t_max=t_max, dt=dt)

    fig, axes = plt.subplots(3, 1, figsize=(8.0, 7.0), sharex=True)

    axes[0].plot(h_open["t"], h_open["x"], color="#d62728", lw=1.5,
                 label="Open loop", alpha=0.8)
    axes[0].plot(h_pid["t"], h_pid["x"], color="#2ca02c", lw=1.5,
                 label="PID")
    axes[0].set_ylabel("Displacement x (m)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(h_open["t"], h_open["v"], color="#d62728", lw=1.5, alpha=0.8)
    axes[1].plot(h_pid["t"], h_pid["v"], color="#2ca02c", lw=1.5)
    axes[1].set_ylabel(r"Velocity $\dot x$ (m/s)")
    axes[1].grid(alpha=0.3)

    F_ext = F0 * np.sin(omega * h_pid["t"])
    axes[2].plot(h_pid["t"], F_ext, color="gray", lw=1.0,
                 label=r"$F_{ext}(t)$", alpha=0.7)
    axes[2].plot(h_pid["t"], h_pid["u"], color="#2ca02c", lw=1.5,
                 label="u(t) (PID)")
    axes[2].set_ylabel("Force (N)")
    axes[2].set_xlabel("Time (s)")
    axes[2].legend(loc="upper right")
    axes[2].grid(alpha=0.3)

    fig.suptitle(
        rf"PID — harmonic excitation at resonance ($\omega = \omega_n = {OMEGA_N:.1f}$ rad/s)"
    )
    fig.tight_layout()
    fig.savefig(figdir / "pid_simulation.png", dpi=140)
    plt.close(fig)

    last4 = h_pid["t"] >= (t_max - 4.0)
    return {
        "peak_x": float(np.max(np.abs(h_pid["x"][last4]))),
        "rms_x": float(np.sqrt(np.mean(h_pid["x"][last4] ** 2))),
        "u_peak": float(np.max(np.abs(h_pid["u"]))),
    }


def plot_comparison(fis, pid: PID, figdir: Path) -> dict[str, dict[str, float]]:
    omega = OMEGA_N
    t_max = 12.0
    dt = 0.005

    h_open = simulate(omega, t_max=t_max, dt=dt, fis=None)
    h_fuzzy = simulate(omega, t_max=t_max, dt=dt, fis=fis)
    h_pid = simulate_pid(pid, omega, t_max=t_max, dt=dt)

    fig, axes = plt.subplots(2, 1, figsize=(8.5, 6.5), sharex=True)

    axes[0].plot(h_open["t"], h_open["x"], color="#d62728", lw=1.4,
                 label="Open loop", alpha=0.7)
    axes[0].plot(h_fuzzy["t"], h_fuzzy["x"], color="#1f77b4", lw=1.6,
                 label="Fuzzy")
    axes[0].plot(h_pid["t"], h_pid["x"], color="#2ca02c", lw=1.6,
                 label="PID")
    axes[0].set_ylabel("Displacement x (m)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(h_fuzzy["t"], h_fuzzy["u"], color="#1f77b4", lw=1.6,
                 label="Fuzzy")
    axes[1].plot(h_pid["t"], h_pid["u"], color="#2ca02c", lw=1.6,
                 label="PID")
    axes[1].axhline(U_MAX, color="gray", linestyle=":", alpha=0.5,
                    label=r"$\pm U_{\max}$")
    axes[1].axhline(-U_MAX, color="gray", linestyle=":", alpha=0.5)
    axes[1].set_ylabel("Control force u (N)")
    axes[1].set_xlabel("Time (s)")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.3)

    fig.suptitle("Fuzzy vs. PID — comparison at resonance")
    fig.tight_layout()
    fig.savefig(figdir / "comparison_simulation.png", dpi=140)
    plt.close(fig)

    last4 = h_open["t"] >= (t_max - 4.0)
    return {
        "open": {
            "peak": float(np.max(np.abs(h_open["x"][last4]))),
            "rms": float(np.sqrt(np.mean(h_open["x"][last4] ** 2))),
            "u_peak": 0.0,
        },
        "fuzzy": {
            "peak": float(np.max(np.abs(h_fuzzy["x"][last4]))),
            "rms": float(np.sqrt(np.mean(h_fuzzy["x"][last4] ** 2))),
            "u_peak": float(np.max(np.abs(h_fuzzy["u"]))),
        },
        "pid": {
            "peak": float(np.max(np.abs(h_pid["x"][last4]))),
            "rms": float(np.sqrt(np.mean(h_pid["x"][last4] ** 2))),
            "u_peak": float(np.max(np.abs(h_pid["u"]))),
        },
    }


def plot_comparison_frequency(fis, pid: PID, figdir: Path) -> None:
    omegas = np.linspace(0.4 * OMEGA_N, 1.8 * OMEGA_N, 18)
    t_max = 18.0
    dt = 0.005

    amp_open = np.zeros_like(omegas)
    amp_fuzzy = np.zeros_like(omegas)
    amp_pid = np.zeros_like(omegas)

    for i, om in enumerate(omegas):
        h_o = simulate(om, t_max=t_max, dt=dt, fis=None)
        h_f = simulate(om, t_max=t_max, dt=dt, fis=fis)
        h_p = simulate_pid(pid, om, t_max=t_max, dt=dt)
        last = h_o["t"] >= (t_max - 4.0)
        amp_open[i] = np.max(np.abs(h_o["x"][last]))
        amp_fuzzy[i] = np.max(np.abs(h_f["x"][last]))
        amp_pid[i] = np.max(np.abs(h_p["x"][last]))

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ax.plot(omegas / OMEGA_N, amp_open, color="#d62728", marker="o",
            lw=1.8, markersize=5, label="Open loop")
    ax.plot(omegas / OMEGA_N, amp_fuzzy, color="#1f77b4", marker="o",
            lw=1.8, markersize=5, label="Fuzzy")
    ax.plot(omegas / OMEGA_N, amp_pid, color="#2ca02c", marker="o",
            lw=1.8, markersize=5, label="PID")
    ax.axvline(1.0, color="gray", linestyle=":", alpha=0.6,
               label=r"$\omega_n$")
    ax.set_xlabel(r"$\omega/\omega_n$")
    ax.set_ylabel("Steady-state amplitude (m)")
    ax.set_title("Frequency response — open loop vs. Fuzzy vs. PID")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figdir / "comparison_frequency.png", dpi=140)
    plt.close(fig)


# ----- Entry point ----------------------------------------------------------


def main() -> None:
    np.random.seed(0)
    fis = build_fis()
    pid = PID(**PID_GAINS)

    figdir = Path(__file__).parent / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    plot_pid_simulation(pid, figdir)
    metrics = plot_comparison(fis, pid, figdir)
    plot_comparison_frequency(fis, pid, figdir)

    print(f"Plant: m={M} kg, k={K} N/m, zeta=0.02, omega_n={OMEGA_N:.1f} rad/s")
    print(
        f"PID gains: K_p={PID_GAINS['K_p']}, "
        f"K_i={PID_GAINS['K_i']}, K_d={PID_GAINS['K_d']}"
    )
    print()
    print("Steady-state metrics at resonance (last 4 s):")
    o = metrics["open"]
    f = metrics["fuzzy"]
    p = metrics["pid"]
    print(f"  Open loop:  peak={o['peak']:.4f} m,  rms={o['rms']:.4f} m")
    print(
        f"  Fuzzy:      peak={f['peak']:.4f} m,  rms={f['rms']:.4f} m,  "
        f"peak |u|={f['u_peak']:.3f} N"
    )
    print(
        f"  PID:        peak={p['peak']:.4f} m,  rms={p['rms']:.4f} m,  "
        f"peak |u|={p['u_peak']:.3f} N"
    )
    print()
    print("Reduction vs. open loop:")
    print(
        f"  Fuzzy:  {100*(1-f['peak']/o['peak']):.1f}% peak,  "
        f"{100*(1-f['rms']/o['rms']):.1f}% RMS"
    )
    print(
        f"  PID:    {100*(1-p['peak']/o['peak']):.1f}% peak,  "
        f"{100*(1-p['rms']/o['rms']):.1f}% RMS"
    )
    print()
    print(f"Figures saved to: {figdir}")


if __name__ == "__main__":
    main()
