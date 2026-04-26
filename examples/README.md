# Examples

Standalone tutorial / demo scripts. Each file is self-contained and consumes the `fuzzy/` package at the repository root.

## Convention

- One file per concept (Mamdani, Sugeno, Tsukamoto, ANFIS, …).
- Top-of-file docstring explains what the script demonstrates.
- Set seeds at the top: `numpy.random.default_rng(0)`, `torch.manual_seed(0)`.
- Print or plot — no global state, no library-style abstractions.

## Running

Run from the repository root so the `fuzzy` package is importable:

```bash
python examples/<script>.py
```
