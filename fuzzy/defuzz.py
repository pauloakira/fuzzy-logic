"""Defuzzification methods."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def centroid(y: ArrayLike, mu: ArrayLike) -> float:
    """Centroid (center of gravity) defuzzification on a discretized universe.

    On a degenerate aggregated output (mu identically zero), returns the
    midpoint of the universe `y` as a defined fallback.
    """
    y = np.asarray(y, dtype=float)
    mu = np.asarray(mu, dtype=float)
    total = float(np.sum(mu))
    if total < 1e-12:
        return float((y[0] + y[-1]) / 2.0)
    return float(np.sum(y * mu) / total)
