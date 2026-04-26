"""t-norms, t-conorms, and complements.

Default Mamdani: `t_min` for AND, `s_max` for OR, `standard_complement` for NOT.
Other families (product / probabilistic, Lukasiewicz) included for convenience.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def t_min(a: ArrayLike, b: ArrayLike) -> NDArray[np.float64]:
    """Zadeh / Gödel t-norm: min(a, b)."""
    return np.minimum(np.asarray(a, dtype=float), np.asarray(b, dtype=float))


def s_max(a: ArrayLike, b: ArrayLike) -> NDArray[np.float64]:
    """Zadeh / Gödel t-conorm: max(a, b)."""
    return np.maximum(np.asarray(a, dtype=float), np.asarray(b, dtype=float))


def t_product(a: ArrayLike, b: ArrayLike) -> NDArray[np.float64]:
    """Product t-norm: a * b."""
    return np.asarray(a, dtype=float) * np.asarray(b, dtype=float)


def s_probabilistic(a: ArrayLike, b: ArrayLike) -> NDArray[np.float64]:
    """Probabilistic-sum t-conorm: a + b - a*b."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return a + b - a * b


def standard_complement(a: ArrayLike) -> NDArray[np.float64]:
    """Standard complement: 1 - a."""
    return 1.0 - np.asarray(a, dtype=float)
