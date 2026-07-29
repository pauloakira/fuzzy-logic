"""Response metrics, defined once.

The `tau` guard exists because of a real bug in this repo: exercise 2 measured a
"steady-state" window of the last 4 s of a 12 s run on a plant whose own decay
time constant is `1 / (zeta * omega_n) = 5 s`. The uncontrolled reference was
therefore still 9 % below its true amplitude, while the controlled cases had
settled — a one-sided bias in every reported reduction figure.

Passing `tau=diagram.slowest_tau()` turns that class of mistake into a warning
instead of a silently wrong number.
"""

from __future__ import annotations

import warnings

import numpy as np
from numpy.typing import NDArray

from fuzzy.sim import Log

SETTLE_FACTOR = 4.0
"""Time constants of settling required before a window counts as steady state."""


def steady_state(
    log: Log,
    key: str,
    *,
    window: float,
    index: int | None = None,
    tau: float | None = None,
) -> dict[str, float]:
    """Peak / RMS / mean of `key` over the final `window` seconds.

    Warns when fewer than `SETTLE_FACTOR * tau` seconds of settling precede the
    window, i.e. when the "steady state" is not one.
    """
    t = log.t
    if window <= 0 or window > t[-1] - t[0]:
        raise ValueError("`window` must be positive and shorter than the run")

    settled_for = (t[-1] - window) - t[0]
    if tau is not None and settled_for < SETTLE_FACTOR * tau:
        warnings.warn(
            f"window is not steady state: only {settled_for:.2f} s of settling "
            f"precede it, but tau={tau:.2f} s needs "
            f"{SETTLE_FACTOR * tau:.2f} s. Increase t_max to at least "
            f"{t[0] + SETTLE_FACTOR * tau + window:.1f} s.",
            UserWarning,
            stacklevel=2,
        )

    y = np.asarray(log[key], dtype=float)
    if y.ndim > 1:
        if index is None:
            raise ValueError(f"{key!r} is vector-valued; pass `index`")
        y = y[:, index]
    seg = y[t >= t[-1] - window]
    return {
        "peak": float(np.max(np.abs(seg))),
        "rms": float(np.sqrt(np.mean(seg**2))),
        "mean": float(np.mean(seg)),
    }


def reduction(baseline: float, controlled: float) -> float:
    """Fractional reduction of `controlled` against `baseline`."""
    if baseline == 0.0:
        raise ValueError("`baseline` must be non-zero")
    return 1.0 - controlled / baseline


def amplitude(log: Log, key: str, *, window: float, index: int | None = None) -> float:
    """Peak magnitude over the final `window` seconds — for frequency sweeps."""
    y = np.asarray(log[key], dtype=float)
    if y.ndim > 1:
        if index is None:
            raise ValueError(f"{key!r} is vector-valued; pass `index`")
        y = y[:, index]
    return float(np.max(np.abs(y[log.t >= log.t[-1] - window])))


def envelope_decay(t: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    """Fit `exp(-rate * t)` to the peaks of a decaying signal; return `rate`."""
    peaks = [
        i for i in range(1, len(y) - 1) if abs(y[i]) > max(abs(y[i - 1]), abs(y[i + 1]))
    ]
    if len(peaks) < 2:
        raise ValueError("need at least two peaks to fit an envelope")
    idx = np.array(peaks)
    slope, _ = np.polyfit(t[idx], np.log(np.abs(y[idx])), 1)
    return float(-slope)
