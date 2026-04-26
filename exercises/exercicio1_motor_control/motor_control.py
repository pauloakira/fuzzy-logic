"""Predictive fuzzy logic motor speed controller (Mamdani approach).

PCS5708 — Exercício 1 — Controle de velocidade de motor DC.

Plant
-----
- Motor speed omega in [0, 1000] rpm; voltage V in [0, 100] V.
- Steady-state speed: omega_ss(V) = 10 * V (so V = 100 V → omega_ss = 1000 rpm).
- Speed slews toward omega_ss at rate-limited |d omega/dt| <= 1 rpm/s.
- Voltage updates at rate equal to FIS output (capped at ±1 V/s).

Controller
----------
- Mamdani FIS with two inputs (velocidade, alimentacao) and one output (aceleracao).
- Membership functions: shouldered triangulars over [0, 1000], [0, 100], [-1, 1].
- 3 x 3 rule base (see RULES below).
- Inference: min t-norm for AND, max aggregation, centroid defuzzification.

Outputs
-------
- figures/mf_velocidade.png
- figures/mf_alimentacao.png
- figures/mf_aceleracao.png
- figures/control_surface.png
- figures/simulation.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Allow `python exercises/exercicio1_motor_control/motor_control.py` from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fuzzy.fis import MamdaniFIS  # noqa: E402
from fuzzy.membership import left_shoulder, right_shoulder, triangular  # noqa: E402


# ----- Membership functions -------------------------------------------------


def velocidade_baixa(x):
    return left_shoulder(x, 0, 500)


def velocidade_media(x):
    return triangular(x, 0, 500, 1000)


def velocidade_alta(x):
    return right_shoulder(x, 500, 1000)


def alimentacao_baixa(x):
    return left_shoulder(x, 0, 50)


def alimentacao_media(x):
    return triangular(x, 0, 50, 100)


def alimentacao_alta(x):
    return right_shoulder(x, 50, 100)


def aceleracao_freio(x):
    return left_shoulder(x, -1, 0)


def aceleracao_neutro(x):
    return triangular(x, -1, 0, 1)


def aceleracao_acelerar(x):
    return right_shoulder(x, 0, 1)


# ----- FIS construction -----------------------------------------------------

INPUTS = {
    "velocidade": {
        "Baixa": velocidade_baixa,
        "Media": velocidade_media,
        "Alta": velocidade_alta,
    },
    "alimentacao": {
        "Baixa": alimentacao_baixa,
        "Media": alimentacao_media,
        "Alta": alimentacao_alta,
    },
}

OUTPUT_TERMS = {
    "Freio": aceleracao_freio,
    "Neutro": aceleracao_neutro,
    "Acelerar": aceleracao_acelerar,
}

OUTPUT_UNIVERSE = np.linspace(-1.0, 1.0, 401)

# Rule base (rows = velocidade, columns = alimentacao):
#                | Alim Baixa | Alim Media | Alim Alta
# Vel Baixa      | Acelerar   | Acelerar   | Neutro
# Vel Media      | Acelerar   | Neutro     | Freio
# Vel Alta       | Neutro     | Freio      | Freio
RULES = [
    ({"velocidade": "Baixa", "alimentacao": "Baixa"}, "Acelerar"),
    ({"velocidade": "Baixa", "alimentacao": "Media"}, "Acelerar"),
    ({"velocidade": "Baixa", "alimentacao": "Alta"}, "Neutro"),
    ({"velocidade": "Media", "alimentacao": "Baixa"}, "Acelerar"),
    ({"velocidade": "Media", "alimentacao": "Media"}, "Neutro"),
    ({"velocidade": "Media", "alimentacao": "Alta"}, "Freio"),
    ({"velocidade": "Alta", "alimentacao": "Baixa"}, "Neutro"),
    ({"velocidade": "Alta", "alimentacao": "Media"}, "Freio"),
    ({"velocidade": "Alta", "alimentacao": "Alta"}, "Freio"),
]


def build_fis() -> MamdaniFIS:
    return MamdaniFIS(
        inputs=INPUTS,
        output_terms=OUTPUT_TERMS,
        output_universe=OUTPUT_UNIVERSE,
        rules=RULES,
    )


# ----- Plant simulation -----------------------------------------------------


def simulate(
    fis: MamdaniFIS,
    omega0: float = 0.0,
    V0: float = 0.0,
    t_max: float = 300.0,
    dt: float = 1.0,
    k: float = 10.0,
    omega_max_rate: float = 1.0,
) -> dict[str, np.ndarray]:
    """Closed-loop simulation.

    At each step, the FIS produces an acceleration command in [-1, +1].
    The voltage updates at rate `acc` V/s; the motor speed slews toward `k * V`
    at a rate capped by `omega_max_rate` rpm/s.
    """
    n_steps = int(t_max / dt) + 1
    t = np.zeros(n_steps)
    omega = np.zeros(n_steps)
    V = np.zeros(n_steps)
    acc = np.zeros(n_steps)

    omega[0] = omega0
    V[0] = V0

    for i in range(n_steps - 1):
        a = fis.evaluate(
            {"velocidade": float(omega[i]), "alimentacao": float(V[i])}
        )
        acc[i] = a
        omega_eq = k * V[i]
        natural = float(np.clip(omega_eq - omega[i], -omega_max_rate, omega_max_rate))
        omega[i + 1] = float(np.clip(omega[i] + natural * dt, 0.0, 1000.0))
        V[i + 1] = float(np.clip(V[i] + a * dt, 0.0, 100.0))
        t[i + 1] = t[i] + dt

    acc[-1] = fis.evaluate(
        {"velocidade": float(omega[-1]), "alimentacao": float(V[-1])}
    )

    return {"t": t, "omega": omega, "V": V, "acc": acc}


# ----- Plotting -------------------------------------------------------------

COLOR_LOW = "C3"     # red
COLOR_MID = "C0"     # blue
COLOR_HIGH = "C2"    # green


def _styled_axes(ax, ylim=(-0.05, 1.1)):
    ax.set_ylim(*ylim)
    ax.grid(alpha=0.3)


def plot_mf_velocidade(figdir: Path) -> None:
    x = np.linspace(0, 1000, 1001)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(x, velocidade_baixa(x), label="Baixa", color=COLOR_LOW, lw=2)
    ax.plot(x, velocidade_media(x), label="Média", color=COLOR_MID, lw=2)
    ax.plot(x, velocidade_alta(x), label="Alta", color=COLOR_HIGH, lw=2)
    ax.set_xlabel("rpm")
    ax.set_ylabel(r"$\mu(\omega)$")
    ax.set_title("Entrada: Velocidade")
    ax.legend(loc="upper center", ncol=3, frameon=False)
    _styled_axes(ax)
    fig.tight_layout()
    fig.savefig(figdir / "mf_velocidade.png", dpi=140)
    plt.close(fig)


def plot_mf_alimentacao(figdir: Path) -> None:
    x = np.linspace(0, 100, 1001)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(x, alimentacao_baixa(x), label="Baixa", color=COLOR_LOW, lw=2)
    ax.plot(x, alimentacao_media(x), label="Média", color=COLOR_MID, lw=2)
    ax.plot(x, alimentacao_alta(x), label="Alta", color=COLOR_HIGH, lw=2)
    ax.set_xlabel("V")
    ax.set_ylabel(r"$\mu(V)$")
    ax.set_title("Entrada: Alimentação")
    ax.legend(loc="upper center", ncol=3, frameon=False)
    _styled_axes(ax)
    fig.tight_layout()
    fig.savefig(figdir / "mf_alimentacao.png", dpi=140)
    plt.close(fig)


def plot_mf_aceleracao(figdir: Path) -> None:
    x = np.linspace(-1, 1, 1001)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(x, aceleracao_freio(x), label="Freio", color=COLOR_LOW, lw=2)
    ax.plot(x, aceleracao_neutro(x), label="Neutro", color=COLOR_MID, lw=2)
    ax.plot(x, aceleracao_acelerar(x), label="Aceleração", color=COLOR_HIGH, lw=2)
    ax.set_xlabel("rpm/s")
    ax.set_ylabel(r"$\mu(\dot\omega)$")
    ax.set_title("Saída: Aceleração")
    ax.legend(loc="upper center", ncol=3, frameon=False)
    _styled_axes(ax)
    fig.tight_layout()
    fig.savefig(figdir / "mf_aceleracao.png", dpi=140)
    plt.close(fig)


def plot_control_surface(fis: MamdaniFIS, figdir: Path) -> None:
    omegas = np.linspace(0, 1000, 41)
    Vs = np.linspace(0, 100, 41)
    Z = np.zeros((len(omegas), len(Vs)))
    for i, om in enumerate(omegas):
        for j, v in enumerate(Vs):
            Z[i, j] = fis.evaluate(
                {"velocidade": float(om), "alimentacao": float(v)}
            )

    fig = plt.figure(figsize=(7.5, 5.4))
    ax = fig.add_subplot(111, projection="3d")
    OM, VV = np.meshgrid(Vs, omegas)
    surf = ax.plot_surface(
        OM, VV, Z, cmap="RdYlGn", edgecolor="none", alpha=0.95
    )
    ax.set_xlabel("Alimentação (V)")
    ax.set_ylabel("Velocidade (rpm)")
    ax.set_zlabel("Aceleração (rpm/s)")
    ax.set_title("Superfície de controle")
    fig.colorbar(surf, shrink=0.6, aspect=12, label="rpm/s")
    fig.tight_layout()
    fig.savefig(figdir / "control_surface.png", dpi=140)
    plt.close(fig)


def plot_simulation(fis: MamdaniFIS, figdir: Path) -> None:
    h_low = simulate(fis, omega0=0, V0=0, t_max=800, dt=1.0)
    h_high = simulate(fis, omega0=1000, V0=100, t_max=800, dt=1.0)

    fig, axes = plt.subplots(3, 1, figsize=(7.5, 6.4), sharex=True)

    axes[0].plot(h_low["t"], h_low["omega"], color="C0", lw=1.8,
                 label=r"Início (0, 0)")
    axes[0].plot(h_high["t"], h_high["omega"], color="C3", lw=1.8,
                 label=r"Início (1000, 100)")
    axes[0].axhline(500, color="gray", linestyle=":", alpha=0.6,
                    label="Equilíbrio")
    axes[0].set_ylabel("Velocidade (rpm)")
    axes[0].legend(loc="center right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(h_low["t"], h_low["V"], color="C0", lw=1.8)
    axes[1].plot(h_high["t"], h_high["V"], color="C3", lw=1.8)
    axes[1].axhline(50, color="gray", linestyle=":", alpha=0.6)
    axes[1].set_ylabel("Alimentação (V)")
    axes[1].grid(alpha=0.3)

    axes[2].plot(h_low["t"], h_low["acc"], color="C0", lw=1.8)
    axes[2].plot(h_high["t"], h_high["acc"], color="C3", lw=1.8)
    axes[2].axhline(0, color="gray", linestyle=":", alpha=0.6)
    axes[2].set_ylabel("Aceleração (rpm/s)")
    axes[2].set_xlabel("Tempo (s)")
    axes[2].grid(alpha=0.3)

    fig.suptitle("Simulação de malha fechada — duas condições iniciais")
    fig.tight_layout()
    fig.savefig(figdir / "simulation.png", dpi=140)
    plt.close(fig)


# ----- Entry point ----------------------------------------------------------


def main() -> None:
    np.random.seed(0)
    fis = build_fis()

    here = Path(__file__).parent
    figdir = here / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    plot_mf_velocidade(figdir)
    plot_mf_alimentacao(figdir)
    plot_mf_aceleracao(figdir)
    plot_control_surface(fis, figdir)
    plot_simulation(fis, figdir)

    samples = [(0, 0), (200, 20), (500, 50), (700, 70), (900, 90), (1000, 100)]
    print("(velocidade, alimentação) → aceleração")
    for om, v in samples:
        a = fis.evaluate({"velocidade": float(om), "alimentacao": float(v)})
        print(f"  ({om:>4d} rpm, {v:>3d} V) → {a:+.4f} rpm/s")

    print(f"\nFigures saved to: {figdir}")


if __name__ == "__main__":
    main()
