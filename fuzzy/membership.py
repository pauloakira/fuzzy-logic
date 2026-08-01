"""Membership functions: triangular, trapezoidal, shoulders, Gaussian."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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


# ----- Declarative terms -----------------------------------------------------

MF_REGISTRY: dict[str, Callable[..., NDArray[np.float64]]] = {
    "triangular": triangular,
    "trapezoidal": trapezoidal,
    "left_shoulder": left_shoulder,
    "right_shoulder": right_shoulder,
    "gaussian": gaussian,
}
"""Membership-function kinds addressable by name, for specs and editor palettes."""

ARITY = {
    "triangular": 3,
    "trapezoidal": 4,
    "left_shoulder": 2,
    "right_shoulder": 2,
    "gaussian": 2,
}


def _check_params(kind: str, p: tuple[float, ...]) -> str | None:
    """Enforce each MF's stated precondition. Returns a message, or None if fine.

    These are the constraints the module docstrings already declare. They matter
    because violating them is silent rather than loud: a shoulder with `a == b`
    divides by zero and yields NaN at one input, which then propagates into
    inference and — because comparisons against NaN are False — slips past the
    strong-partition check as well.
    """
    if kind in ("triangular", "trapezoidal"):
        if list(p) != sorted(p):
            names = "a <= b <= c" if kind == "triangular" else "a <= b <= c <= d"
            return f"{kind} requires {names}, got {list(p)}"
    elif kind in ("left_shoulder", "right_shoulder"):
        if not p[1] > p[0]:
            return f"{kind} requires b > a, got a={p[0]}, b={p[1]}"
    elif kind == "gaussian":
        if not p[1] > 0:
            return f"gaussian requires sigma > 0, got sigma={p[1]}"
    return None


class TermError(ValueError):
    """A term is malformed: unknown MF kind, wrong parameter count, or parameters
    that violate the kind's stated precondition (ordering, or a positive sigma)."""


@dataclass(frozen=True)
class Term:
    """One linguistic term, described as data rather than as a closure.

    A `Term` is callable, so it drops into `MamdaniFIS` wherever a plain
    membership callable was accepted before — but unlike a closure it can be
    saved, inspected, and edited.
    """

    kind: str
    params: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.kind not in MF_REGISTRY:
            raise TermError(
                f"unknown membership kind {self.kind!r}; "
                f"known: {sorted(MF_REGISTRY)}"
            )
        expected = ARITY[self.kind]
        if len(self.params) != expected:
            raise TermError(
                f"{self.kind} takes {expected} parameters, got {len(self.params)}"
            )
        problem = _check_params(self.kind, self.params)
        if problem:
            raise TermError(problem)

    def __call__(self, x: ArrayLike) -> NDArray[np.float64]:
        return MF_REGISTRY[self.kind](x, *self.params)

    def to_spec(self) -> dict[str, Any]:
        return {"kind": self.kind, "params": list(self.params)}

    @classmethod
    def from_spec(cls, data: Mapping[str, Any]) -> Term:
        try:
            return cls(str(data["kind"]), tuple(float(p) for p in data["params"]))
        except KeyError as exc:
            raise TermError(f"term entry missing {exc.args[0]!r}") from None


@dataclass(frozen=True)
class Variable:
    """A linguistic variable: named terms over a universe of discourse."""

    name: str
    low: float
    high: float
    terms: Mapping[str, Term]

    def __post_init__(self) -> None:
        if self.high <= self.low:
            raise TermError(f"{self.name}: `high` must exceed `low`")
        if not self.terms:
            raise TermError(f"{self.name}: needs at least one term")

    def __getitem__(self, term: str) -> Term:
        try:
            return self.terms[term]
        except KeyError:
            raise TermError(
                f"{self.name} has no term {term!r}; has: {sorted(self.terms)}"
            ) from None

    def universe(self, n: int = 401) -> NDArray[np.float64]:
        return np.linspace(self.low, self.high, n)

    def partition_error(self, n: int = 1001) -> float:
        """Max deviation of `sum(mu)` from 1 across the universe.

        Zero for a strong partition. Useful as an editor-side warning when a
        hand-edited term set leaves a gap or an overlap.
        """
        grid = self.universe(n)
        total = np.asarray(sum(t(grid) for t in self.terms.values()), dtype=float)
        if not np.all(np.isfinite(total)):
            # NaN compares False against any threshold, so reporting it as a
            # finite deviation is what keeps it from hiding from the caller.
            return float("inf")
        return float(np.max(np.abs(total - 1.0)))

    def to_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "low": self.low,
            "high": self.high,
            "terms": {k: v.to_spec() for k, v in self.terms.items()},
        }

    @classmethod
    def from_spec(cls, data: Mapping[str, Any]) -> Variable:
        return cls(
            name=str(data["name"]),
            low=float(data["low"]),
            high=float(data["high"]),
            terms={k: Term.from_spec(v) for k, v in data["terms"].items()},
        )

    @classmethod
    def partition(
        cls,
        name: str,
        low: float,
        high: float,
        terms: Sequence[str] = ("NG", "NP", "Z", "PP", "PG"),
    ) -> Variable:
        """The standard strong partition: shoulders at the ends, triangles between.

        Term centres are evenly spaced over `[low, high]` and each term meets its
        neighbours at half-membership, so memberships sum to exactly 1 everywhere.
        Works for any term count, so refining a controller from 5 to 7 or 9 terms
        is a one-argument change.
        """
        n = len(terms)
        if n < 3:
            raise TermError("a partition needs at least three terms")
        c = np.linspace(low, high, n)
        built: dict[str, Term] = {}
        for i, label in enumerate(terms):
            if i == 0:
                built[label] = Term("left_shoulder", (float(c[0]), float(c[1])))
            elif i == n - 1:
                built[label] = Term("right_shoulder", (float(c[-2]), float(c[-1])))
            else:
                built[label] = Term(
                    "triangular", (float(c[i - 1]), float(c[i]), float(c[i + 1]))
                )
        return cls(name=name, low=low, high=high, terms=built)
