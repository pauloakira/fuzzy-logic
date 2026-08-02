"""Predictive fuzzy logic motor speed controller (Mamdani approach).

PCS5708 — Exercício 1 — Controle de velocidade de motor DC.

Plant
-----
- Motor speed omega in [0, 1000] rpm; voltage V in [0, 100] V.
- Steady-state speed: omega_ss(V) = 10 * V (so V = 100 V → omega_ss = 1000 rpm).
- Speed slews toward omega_ss at rate-limited |d omega/dt| <= 1 rpm/s.
- Voltage updates at rate equal to FIS output (capped at ±1 V/s).

The plant is **not** LTI: both `omega` and `V` are hard-clamped to their physical
ranges, and `omega`'s natural response is itself rate-limited. `StateSpacePlant`
cannot express either the rate limiter or the state clamps, so this module
defines `MotorPlant`, a small `Block` subclass local to this file (it is not a
reusable plant, so it does not belong in `fuzzy/blocks.py`). It has no
`eigenvalues()` and therefore no RK4 stability guard — see the class docstring.

Controller
----------
- Mamdani FIS with two inputs (velocidade, alimentacao) and one output
  (aceleracao, a voltage rate in V/s — see "Units" below).
- Membership functions: shouldered triangulars over [0, 1000], [0, 100], [-1, 1].
- 3 x 3 rule base (see RULE_TABLE below).
- Inference: min t-norm for AND, max aggregation, centroid defuzzification.

Units
-----
The FIS output is applied as `dV/dt`, in **V/s** — it is the rate at which the
supply voltage is incremented or decremented, per the assignment ("increment or
decrement the supply voltage"). It is *not* a speed rate: `omega_ss = 10 * V`,
so 1 V/s of commanded voltage change corresponds to 10 rpm/s of commanded speed
change, which the plant's own rate limiter then clips to ±1 rpm/s. The two rates
differ by exactly the plant gain of 10 — see the printed summary in `main()` and
REPORT.md §2.

Simulation
----------
The plant and controller are assembled as a block diagram (`fuzzy.sim`) rather
than a hand-rolled integration loop, so the diagram can be saved as a spec file
for the graphical editor. See `docs/design-block-diagram-simulation.md`.

The block-diagram core integrates with RK4 rather than the original script's
explicit Euler at dt=1.0 s. The plant's unclipped time constant is 1 s, so Euler
at dt=1.0 was exactly dead-beat; RK4 resolves the same interval with intermediate
derivative evaluations and gives slightly different trajectories. That is an
accuracy improvement, not a regression — `main()` prints the same summary
statistics the earlier Euler version reported, and they differ only slightly.

Outputs
-------
- figures/mf_velocidade.png
- figures/mf_alimentacao.png
- figures/mf_aceleracao.png
- figures/control_surface.png
- figures/simulation.png
- diagram.json                     — block-diagram spec (editor fixture)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from fuzzy.blocks import FISBlock, MotorPlant, Saturation, Select
from fuzzy.fis import FISSpec, MamdaniFIS
from fuzzy.membership import Variable
from fuzzy.rules import RuleBase
from fuzzy.sim import Diagram, Log, simulate
from fuzzy.spec import save

# ----- Plant parameters -----------------------------------------------------

K = 10.0  # rpm per volt — omega_ss(V) = K * V
OMEGA_MAX = 1000.0  # rpm
V_MAX = 100.0  # V
OMEGA_RATE_MAX = 1.0  # rpm/s — the motor's natural-response rate limit
V_RATE_MAX = 1.0  # V/s — the actuator's rate limit (== the FIS output range)

# ----- Simulation settings --------------------------------------------------

DT = 1.0  # s — control period and integration step, matching the original
T_MAX = 800.0  # s — long enough to see convergence toward (500, 50)


# ----- The plant, as a block -------------------------------------------------


# ----- Linguistic variables ---------------------------------------------------

# `Variable.partition` builds the standard strong partition used by the original
# hand-written membership functions: a descending shoulder, a triangle centred on
# the midpoint, and a rising shoulder, each meeting its neighbour at half-membership.
INPUT_TERMS = ["Baixa", "Media", "Alta"]
OUTPUT_TERMS_ORDER = ["Freio", "Neutro", "Acelerar"]

VEL = Variable.partition("velocidade", 0.0, OMEGA_MAX, INPUT_TERMS)
ALIM = Variable.partition("alimentacao", 0.0, V_MAX, INPUT_TERMS)
ACEL = Variable.partition("aceleracao", -V_RATE_MAX, V_RATE_MAX, OUTPUT_TERMS_ORDER)


# ----- Rule base ---------------------------------------------------------------

# Rows: velocidade. Columns: alimentacao.
#                | Alim Baixa | Alim Media | Alim Alta
# Vel Baixa      | Acelerar   | Acelerar   | Neutro
# Vel Media      | Acelerar   | Neutro     | Freio
# Vel Alta       | Neutro     | Freio      | Freio
RULE_TABLE = [
    ["Acelerar", "Acelerar", "Neutro"],
    ["Acelerar", "Neutro", "Freio"],
    ["Neutro", "Freio", "Freio"],
]

RULES = RuleBase.from_table(
    row_var="velocidade",
    col_var="alimentacao",
    row_terms=INPUT_TERMS,
    col_terms=INPUT_TERMS,
    table=RULE_TABLE,
)

OUTPUT_RESOLUTION = 401


def build_fis_spec() -> FISSpec:
    """The controller as data — serialisable, validatable, editable."""
    return FISSpec(
        inputs={"velocidade": VEL, "alimentacao": ALIM},
        output=ACEL,
        rules=RULES,
        resolution=OUTPUT_RESOLUTION,
    )


def build_fis() -> MamdaniFIS:
    """The runnable inference system built from the spec."""
    return build_fis_spec().build()


# ----- Block diagram ------------------------------------------------------------

FUZZY_PORTS = ("velocidade", "alimentacao")
"""Speed and voltage input ports of the fuzzy controller."""

_LAYOUT = {
    "plant": {"x": 360.0, "y": 120.0},
    "vel": {"x": 40.0, "y": 40.0},
    "alim": {"x": 40.0, "y": 200.0},
    "controller": {"x": 200.0, "y": 120.0},
    "actuator": {"x": 560.0, "y": 120.0},
}


def build_diagram(
    x0: float = 0.0,
    v0: float = 0.0,
    name: str = "motor",
) -> Diagram:
    """Assemble the closed loop: plant, phase-plane selects, controller, actuator."""
    d = Diagram(name=name)
    # Every physical limit is stated explicitly rather than left to the block's
    # defaults: omega in [0, 1000] rpm and V in [0, 100] V are part of the
    # problem statement, and the spec file must record them.
    plant = MotorPlant(
        k=K,
        omega_rate_max=OMEGA_RATE_MAX,
        omega_bounds=(0.0, OMEGA_MAX),
        v_bounds=(0.0, V_MAX),
        omega0=x0,
        v0=v0,
        name="plant",
    )
    vel = Select(0, name="vel")
    alim = Select(1, name="alim")
    d.connect(plant, vel)
    d.connect(plant, alim)

    controller = FISBlock(
        build_fis_spec(),
        clip={FUZZY_PORTS[0]: (0.0, OMEGA_MAX), FUZZY_PORTS[1]: (0.0, V_MAX)},
        name="controller",
    )
    d.connect(vel, (controller, FUZZY_PORTS[0]))
    d.connect(alim, (controller, FUZZY_PORTS[1]))

    # The actuator's rate limit is stated once, explicitly, rather than relying
    # on the FIS output universe alone to enforce it.
    actuator = Saturation(-V_RATE_MAX, V_RATE_MAX, name="actuator")
    d.connect(controller, actuator)
    d.connect(actuator, plant)

    present = {b.name for b in d.blocks}
    d.layout.update({k: v for k, v in _LAYOUT.items() if k in present})
    return d


def run(x0: float = 0.0, v0: float = 0.0, t_max: float = T_MAX) -> Log:
    """Build and simulate in one step."""
    d = build_diagram(x0=x0, v0=v0)
    return simulate(d, t_max=t_max, dt_control=DT)


# ----- Plotting -------------------------------------------------------------

COLOR_LOW = "C3"  # red
COLOR_MID = "C0"  # blue
COLOR_HIGH = "C2"  # green


def _styled_axes(ax, ylim=(-0.05, 1.1)):
    ax.set_ylim(*ylim)
    ax.grid(alpha=0.3)


def plot_mf_velocidade(figdir: Path) -> None:
    x = np.linspace(0, OMEGA_MAX, 1001)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(x, VEL["Baixa"](x), label="Baixa", color=COLOR_LOW, lw=2)
    ax.plot(x, VEL["Media"](x), label="Média", color=COLOR_MID, lw=2)
    ax.plot(x, VEL["Alta"](x), label="Alta", color=COLOR_HIGH, lw=2)
    ax.set_xlabel("rpm")
    ax.set_ylabel(r"$\mu(\omega)$")
    ax.set_title("Entrada: Velocidade")
    ax.legend(loc="upper center", ncol=3, frameon=False)
    _styled_axes(ax)
    fig.tight_layout()
    fig.savefig(figdir / "mf_velocidade.png", dpi=140)
    plt.close(fig)


def plot_mf_alimentacao(figdir: Path) -> None:
    x = np.linspace(0, V_MAX, 1001)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(x, ALIM["Baixa"](x), label="Baixa", color=COLOR_LOW, lw=2)
    ax.plot(x, ALIM["Media"](x), label="Média", color=COLOR_MID, lw=2)
    ax.plot(x, ALIM["Alta"](x), label="Alta", color=COLOR_HIGH, lw=2)
    ax.set_xlabel("V")
    ax.set_ylabel(r"$\mu(V)$")
    ax.set_title("Entrada: Alimentação")
    ax.legend(loc="upper center", ncol=3, frameon=False)
    _styled_axes(ax)
    fig.tight_layout()
    fig.savefig(figdir / "mf_alimentacao.png", dpi=140)
    plt.close(fig)


def plot_mf_aceleracao(figdir: Path) -> None:
    x = np.linspace(-V_RATE_MAX, V_RATE_MAX, 1001)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(x, ACEL["Freio"](x), label="Freio", color=COLOR_LOW, lw=2)
    ax.plot(x, ACEL["Neutro"](x), label="Neutro", color=COLOR_MID, lw=2)
    ax.plot(x, ACEL["Acelerar"](x), label="Aceleração", color=COLOR_HIGH, lw=2)
    ax.set_xlabel("V/s")
    ax.set_ylabel(r"$\mu(\dot V)$")
    ax.set_title("Saída: Aceleração")
    ax.legend(loc="upper center", ncol=3, frameon=False)
    _styled_axes(ax)
    fig.tight_layout()
    fig.savefig(figdir / "mf_aceleracao.png", dpi=140)
    plt.close(fig)


def plot_control_surface(fis: MamdaniFIS, figdir: Path) -> None:
    omegas = np.linspace(0, OMEGA_MAX, 41)
    Vs = np.linspace(0, V_MAX, 41)
    Z = np.zeros((len(omegas), len(Vs)))
    for i, om in enumerate(omegas):
        for j, v in enumerate(Vs):
            Z[i, j] = fis.evaluate({"velocidade": float(om), "alimentacao": float(v)})

    fig = plt.figure(figsize=(7.5, 5.4))
    ax = fig.add_subplot(111, projection="3d")
    OM, VV = np.meshgrid(Vs, omegas)
    surf = ax.plot_surface(OM, VV, Z, cmap="RdYlGn", edgecolor="none", alpha=0.95)
    ax.set_xlabel("Alimentação (V)")
    ax.set_ylabel("Velocidade (rpm)")
    ax.set_zlabel("Aceleração (V/s)")
    ax.set_title("Superfície de controle")
    fig.colorbar(surf, shrink=0.6, aspect=12, label="V/s")
    fig.tight_layout()
    fig.savefig(figdir / "control_surface.png", dpi=140)
    plt.close(fig)


def plot_simulation(figdir: Path) -> None:
    h_low = run(x0=0.0, v0=0.0)
    h_high = run(x0=OMEGA_MAX, v0=V_MAX)

    fig, axes = plt.subplots(3, 1, figsize=(7.5, 6.4), sharex=True)

    axes[0].plot(
        h_low.t, h_low.col("plant.y", 0), color="C0", lw=1.8, label=r"Início (0, 0)"
    )
    axes[0].plot(
        h_high.t,
        h_high.col("plant.y", 0),
        color="C3",
        lw=1.8,
        label=r"Início (1000, 100)",
    )
    axes[0].axhline(500, color="gray", linestyle=":", alpha=0.6, label="Equilíbrio")
    axes[0].set_ylabel("Velocidade (rpm)")
    axes[0].legend(loc="center right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(h_low.t, h_low.col("plant.y", 1), color="C0", lw=1.8)
    axes[1].plot(h_high.t, h_high.col("plant.y", 1), color="C3", lw=1.8)
    axes[1].axhline(50, color="gray", linestyle=":", alpha=0.6)
    axes[1].set_ylabel("Alimentação (V)")
    axes[1].grid(alpha=0.3)

    axes[2].plot(h_low.t, h_low["actuator.y"], color="C0", lw=1.8)
    axes[2].plot(h_high.t, h_high["actuator.y"], color="C3", lw=1.8)
    axes[2].axhline(0, color="gray", linestyle=":", alpha=0.6)
    axes[2].set_ylabel("Aceleração (V/s)")
    axes[2].set_xlabel("Tempo (s)")
    axes[2].grid(alpha=0.3)

    fig.suptitle("Simulação de malha fechada — duas condições iniciais")
    fig.tight_layout()
    fig.savefig(figdir / "simulation.png", dpi=140)
    plt.close(fig)


# ----- Entry point ----------------------------------------------------------


def main() -> None:
    fis = build_fis()

    here = Path(__file__).parent
    figdir = here / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    plot_mf_velocidade(figdir)
    plot_mf_alimentacao(figdir)
    plot_mf_aceleracao(figdir)
    plot_control_surface(fis, figdir)
    plot_simulation(figdir)

    spec_path = save(build_diagram(name="ex1_motor"), here / "diagram.json")

    samples = [(0, 0), (200, 20), (500, 50), (700, 70), (900, 90), (1000, 100)]
    print("(velocidade, alimentação) → aceleração (V/s)")
    for om, v in samples:
        a = fis.evaluate({"velocidade": float(om), "alimentacao": float(v)})
        print(f"  ({om:>4d} rpm, {v:>3d} V) → {a:+.4f} V/s")

    h_low = run(x0=0.0, v0=0.0)
    omega_low = h_low.col("plant.y", 0)
    V_low = h_low.col("plant.y", 1)
    diff = np.abs(V_low - omega_low / K)
    imax = int(np.argmax(diff))
    h_high = run(x0=OMEGA_MAX, v0=V_MAX)

    print()
    print(
        f"max|V - omega/{K:g}| = {diff[imax]:.4f} V at t={h_low.t[imax]:.0f} s "
        f"(commanded equilibrium speed running ahead of actual speed)"
    )
    print(
        f"state at t={T_MAX:g} s from (0, 0):        "
        f"omega={omega_low[-1]:.2f} rpm, V={V_low[-1]:.2f} V"
    )
    print(
        f"state at t={T_MAX:g} s from (1000, 100):   "
        f"omega={h_high.col('plant.y', 0)[-1]:.2f} rpm, "
        f"V={h_high.col('plant.y', 1)[-1]:.2f} V"
    )

    print(f"\nFigures saved to: {figdir}")
    print(f"Diagram spec saved to: {spec_path}")


if __name__ == "__main__":
    main()
