"""Membership functions: triangular, trapezoidal, shoulders, Gaussian."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def triangular(x: ArrayLike, a: float, b: float, c: float) -> NDArray[np.float64]:
    """Triangular MF with feet at `a`, `c` and peak at `b`. Requires `a <= b <= c`.

    mu(x) rises linearly from 0 at `a` to 1 at `b`, then falls to 0 at `c`.
    Degenerate cases (a == b or b == c) collapse to a one-sided shape.
    """
    x = np.asarray(x, dtype=float)
    if b > a:
        left = (x - a) / (b - a)
    else:
        left = np.where(x >= a, 1.0, 0.0)
    if c > b:
        right = (c - x) / (c - b)
    else:
        right = np.where(x <= c, 1.0, 0.0)
    return np.clip(np.minimum(left, right), 0.0, 1.0)


def trapezoidal(
    x: ArrayLike, a: float, b: float, c: float, d: float
) -> NDArray[np.float64]:
    """Trapezoidal MF with feet at `a`, `d` and shoulders at `b`, `c`.

    Requires `a <= b <= c <= d`. mu(x) = 1 on `[b, c]`.
    """
    x = np.asarray(x, dtype=float)
    if b > a:
        left = (x - a) / (b - a)
    else:
        left = np.where(x >= a, 1.0, 0.0)
    if d > c:
        right = (d - x) / (d - c)
    else:
        right = np.where(x <= d, 1.0, 0.0)
    return np.clip(np.minimum(np.minimum(left, 1.0), right), 0.0, 1.0)


def left_shoulder(x: ArrayLike, a: float, b: float) -> NDArray[np.float64]:
    """Left shoulder: 1 for x <= a, linear to 0 at b, 0 beyond. Requires `b > a`."""
    x = np.asarray(x, dtype=float)
    return np.clip((b - x) / (b - a), 0.0, 1.0)


def right_shoulder(x: ArrayLike, a: float, b: float) -> NDArray[np.float64]:
    """Right shoulder: 0 for x <= a, linear to 1 at b, 1 beyond. Requires `b > a`."""
    x = np.asarray(x, dtype=float)
    return np.clip((x - a) / (b - a), 0.0, 1.0)


def gaussian(x: ArrayLike, c: float, sigma: float) -> NDArray[np.float64]:
    """Gaussian MF: exp(-(x - c)^2 / (2 sigma^2)). Requires `sigma > 0`."""
    x = np.asarray(x, dtype=float)
    return np.exp(-0.5 * ((x - c) / sigma) ** 2)
