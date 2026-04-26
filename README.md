# Fuzzy Logic

Fuzzy logic research — classical fuzzy inference systems (Mamdani / Sugeno / Tsukamoto) and neuro-fuzzy systems (ANFIS).

## Repository structure

```text
fuzzy-logic/
├── fuzzy/                       # shared Python package
│   ├── __init__.py
│   ├── membership.py            # membership functions
│   ├── operators.py             # t-norms, t-conorms, complements
│   ├── rules.py                 # rule base
│   ├── fis.py                   # Mamdani / Sugeno / Tsukamoto
│   ├── defuzz.py                # defuzzification
│   └── anfis.py                 # ANFIS (PyTorch)
│
├── examples/                    # standalone tutorial / demo scripts
│   └── README.md
│
├── exercises/                   # academic exercises (PCS5708 etc.)
│   └── README.md
│
├── docs/                        # research notes, derivations, design decisions
│   └── research-fuzzy-logic.md
│
├── requirements.txt
├── .gitignore
└── README.md
```

## Setup

Requires Python 3.11+.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running scripts

Examples and exercises import from `fuzzy/` at the repository root. Run from the repo root so the package is importable:

```bash
python examples/tip_mamdani.py
python exercises/<exercise_name>/<name>.py
```

Or set `PYTHONPATH=.` if running from inside a subfolder.
