"""Linear-analysis charts for the LTI blocks of a diagram.

The frequency response, the poles, and the transmission zeros of a continuous
state-space model `x' = A x + B u`, `y = C x + D u`, computed with **NumPy
only** — the repository carries no SciPy on purpose (see `requirements.txt`).

- The frequency response is the resolvent evaluated on a grid,
  `H(jω) = C (jωI − A)^{-1} B + D`, by a direct solve per frequency.
- The poles are the eigenvalues of `A`.
- The transmission zeros of a SISO channel are the roots of the transfer
  function numerator, obtained from the Faddeev–LeVerrier recursion, which
  yields both the characteristic polynomial `det(sI − A)` and the adjugate
  `adj(sI − A)` without a generalized eigenvalue solver.

These are the objects behind the Bode plot and the pole–zero map. Ogata,
*Modern Control Engineering*, 5th ed., §5-4 (pole–zero locations), §7-2 (Bode
plots). See `docs/implementation-output-charts.md`.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def poles(A: ArrayLike) -> NDArray[np.complex128]:
    """Poles of the system, i.e. the eigenvalues of `A`."""
    return np.linalg.eigvals(np.atleast_2d(np.asarray(A, dtype=float)))


def faddeev_leverrier(
    A: NDArray[np.float64],
) -> tuple[NDArray[np.float64], list[NDArray[np.float64]]]:
    """Characteristic polynomial and adjugate coefficient matrices of `A`.

    Returns `(p, Bs)` such that, with `n = A.shape[0]`,

        det(sI − A) = p[0] s^n + p[1] s^{n-1} + ... + p[n],   p[0] = 1,
        adj(sI − A) = Bs[0] s^{n-1} + Bs[1] s^{n-2} + ... + Bs[n-1].

    `Bs` has length `n`. The recursion is the classical Faddeev–LeVerrier
    method, exact in rational arithmetic and stable enough for the small,
    well-scaled plant matrices this tool builds.
    """
    A = np.atleast_2d(np.asarray(A, dtype=float))
    n = A.shape[0]
    eye = np.eye(n)
    Bs = [eye.copy()]          # B_0 = I
    p = [1.0]
    Bk = eye.copy()
    for k in range(1, n + 1):
        ABk = A @ Bk           # A B_{k-1}
        pk = -np.trace(ABk) / k
        p.append(float(pk))
        if k < n:
            Bk = ABk + pk * eye  # B_k = A B_{k-1} + p_k I
            Bs.append(Bk)
    return np.asarray(p, dtype=float), Bs


def zeros(
    A: ArrayLike, b: ArrayLike, c: ArrayLike, d: float = 0.0
) -> NDArray[np.complex128]:
    """Transmission zeros of the SISO channel `(A, b, c, d)`.

    The transfer function is `c (sI − A)^{-1} b + d = num(s) / det(sI − A)`;
    the zeros are the roots of `num`. Using the adjugate,

        num(s) = c · adj(sI − A) · b + d · det(sI − A).
    """
    A = np.atleast_2d(np.asarray(A, dtype=float))
    n = A.shape[0]
    b = np.asarray(b, dtype=float).reshape(n)
    c = np.asarray(c, dtype=float).reshape(n)
    d = float(d)

    p, Bs = faddeev_leverrier(A)
    num = d * p                                 # d · det(sI − A), degree n
    cadjb = np.array([c @ (Bk @ b) for Bk in Bs])  # s^{n-1} ... s^0, length n
    num[1:] = num[1:] + cadjb                   # align onto the s^{n-1..0} tail
    num = np.trim_zeros(num, "f")
    if num.size <= 1:
        return np.array([], dtype=np.complex128)
    return np.roots(num).astype(np.complex128)


def frequency_response(
    A: ArrayLike, B: ArrayLike, C: ArrayLike, D: ArrayLike, omega: ArrayLike
) -> NDArray[np.complex128]:
    """`H(jω)` for every output/input pair, shape `(len(omega), n_out, n_in)`.

    A frequency that coincides with a pole on the imaginary axis makes
    `jωI − A` singular; that one grid point is filled with `inf` rather than
    raising, so an undamped plant still plots.
    """
    A = np.atleast_2d(np.asarray(A, dtype=float))
    n = A.shape[0]
    B = np.asarray(B, dtype=float).reshape(n, -1)
    C = np.atleast_2d(np.asarray(C, dtype=float))
    D = np.atleast_2d(np.asarray(D, dtype=float))
    omega = np.asarray(omega, dtype=float)
    eye = np.eye(n)
    out = np.empty((omega.size, C.shape[0], B.shape[1]), dtype=np.complex128)
    for i, w in enumerate(omega):
        try:
            resolvent_b = np.linalg.solve(1j * w * eye - A, B)
        except np.linalg.LinAlgError:
            out[i] = np.inf
            continue
        out[i] = C @ resolvent_b + D
    return out


def frequency_grid(
    critical: ArrayLike, decades: float = 2.0, n: int = 400
) -> NDArray[np.float64]:
    """A log-spaced `ω` grid spanning `decades` beyond the critical magnitudes.

    `critical` are the poles and zeros; the grid brackets their nonzero
    magnitudes so the Bode plot shows every corner with a couple of decades of
    flat asymptote on each side. With no finite nonzero critical frequency
    (a pure gain, or poles only at the origin) it falls back to `[1e-2, 1e2]`.
    """
    mags = [abs(complex(z)) for z in np.atleast_1d(critical)]
    mags = [m for m in mags if m > 1e-9]
    if not mags:
        lo, hi = -2.0, 2.0
    else:
        # Nudge before rounding out to the enclosing decades. A pole at exactly 1
        # comes back from a numerical Jacobian as 0.999999999995, whose log10 is
        # -2e-12, and `floor` of that is -1 rather than 0 — so an exact model and
        # a linearized one plot the same system over ranges a decade apart.
        snap = 1e-9
        lo = np.floor(np.log10(min(mags)) + snap) - decades
        hi = np.ceil(np.log10(max(mags)) - snap) + decades
    return np.logspace(lo, hi, n)
