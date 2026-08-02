# Fuzzy Logic

[![CI](https://github.com/pauloakira/fuzzy-logic/actions/workflows/ci.yml/badge.svg)](https://github.com/pauloakira/fuzzy-logic/actions/workflows/ci.yml)

Fuzzy logic research — classical fuzzy inference systems (Mamdani / Sugeno / Tsukamoto) and neuro-fuzzy systems (ANFIS), plus a small block-diagram simulation core for putting controllers in a loop with a plant.

## Repository structure

```text
fuzzy-logic/
├── fuzzy/                       # shared Python package
│   ├── membership.py            # membership functions
│   ├── operators.py             # t-norms, t-conorms, complements
│   ├── rules.py                 # rule base                      (stub)
│   ├── fis.py                   # Mamdani / Sugeno / Tsukamoto
│   ├── defuzz.py                # defuzzification
│   ├── anfis.py                 # ANFIS (PyTorch)                (stub)
│   ├── blocks.py                # simulation blocks: plants, sources, controllers
│   ├── sim.py                   # block diagrams, scheduling, RK4, logging
│   ├── metrics.py               # steady-state response metrics
│   └── spec.py                  # declarative diagram specs (JSON) + registry
│
├── examples/                    # standalone tutorial / demo scripts
├── exercises/                   # academic exercises (PCS5708 etc.)
├── tests/unit/                  # pytest unit tests
├── docs/                        # research notes and design decisions
│   ├── research-fuzzy-logic.md
│   ├── research-classical-control.md
│   ├── research-solid-mech-dynamics.md
│   └── design-block-diagram-simulation.md
│
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Setup

Requires Python 3.11+.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

The editable install is what makes `import fuzzy` work from any directory — scripts do not manipulate `sys.path`. For the test and lint tooling:

```bash
pip install -e ".[dev]"
```

`torch` is only needed for the neuro-fuzzy track and is not installed by default:

```bash
pip install -e ".[anfis]"
```

## Running scripts

From the repository root:

```bash
python exercises/exercicio1_motor_control/motor_control.py
python exercises/exercicio2_sdof_vibration_control/sdof_vibration.py
python exercises/exercicio2_sdof_vibration_control/pid_comparison.py
```

## Tests and lint

```bash
pytest -q
ruff check fuzzy/ tests/ exercises/
mypy
```

These three commands are exactly what CI runs, on Python 3.11 / 3.12 / 3.13
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

`tests/unit/` covers the library in pieces; `tests/integration/` pins the numbers
published in the exercise reports, so a refactor that quietly moves a documented
result fails in CI rather than in a reader's eye.

`ruff format` is deliberately **not** enforced: the rule matrices in the exercise
scripts use manual column alignment that reads as a table, and the formatter would
flatten it. Lint, types, and tests are gated; layout is not.

## Block editor API

The block editor's backend is a small FastAPI app. It is optional — `fuzzy.sim`
never imports a web framework, so a headless simulation run does not need it:

```bash
pip install -e ".[editor]"
uvicorn editor.api:app --reload
```

`GET /api/palette` describes every registered block type, `GET /api/diagrams`
lists the spec files in the repo, and `POST /api/validate` and `POST /api/simulate`
take a spec document and return structured problems or decimated signals. It is
tested headlessly in `tests/api/` — no browser required.

## Block diagrams

Simulations are assembled as block diagrams rather than hand-written integration
loops, so the same plant can be driven by different controllers without copying
the loop:

```python
from fuzzy.blocks import Harmonic, Sum, sdof_plant
from fuzzy.sim import Diagram, simulate

d = Diagram()
plant = sdof_plant(m=1.0, c=0.4, k=100.0)
total = Sum(("ext", "ctrl"))
d.connect(Harmonic(amplitude=1.0, omega=10.0), (total, "ext"))
d.connect(total, plant)
...
log = simulate(d, t_max=40.0, dt_control=0.005)
```

A diagram round-trips to a plain JSON spec (`fuzzy.spec.save` / `load`), which is
the representation the planned graphical editor reads and writes. See
[`docs/design-block-diagram-simulation.md`](docs/design-block-diagram-simulation.md).
