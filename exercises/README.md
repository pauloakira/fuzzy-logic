# Exercises

Academic exercises (PCS5708 and similar). Each exercise lives in its own subfolder.

## Convention

```text
exercises/<exercise_name>/
├── README.md      # short description: what the exercise asks, how to run
├── REPORT.md      # full solution writeup — math, plots, conclusions
└── <name>.py      # the runnable solution
```

## Running

Run from the repository root so the `fuzzy` package is importable:

```bash
python exercises/<exercise_name>/<name>.py
```
