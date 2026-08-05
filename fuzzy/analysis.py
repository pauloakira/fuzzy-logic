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


def _cross(x: NDArray[np.float64], y: NDArray[np.float64], level: float) -> list[float]:
    """Where `y` crosses `level`, linearly interpolated, in the units of `x`.

    `x` is expected to be `log10(omega)`: a Bode grid is log-spaced, so
    interpolating in the log is what makes a crossing between two grid points
    land where the curve actually crosses rather than a decade off.
    """
    out: list[float] = []
    d = y - level
    for i in range(len(d) - 1):
        a, b = d[i], d[i + 1]
        if not np.isfinite(a) or not np.isfinite(b) or a == b:
            continue
        if (a <= 0.0 < b) or (b <= 0.0 < a):
            out.append(float(x[i] + (x[i + 1] - x[i]) * (-a / (b - a))))
    return out


def margins(omega: ArrayLike, L: ArrayLike) -> dict[str, float | None]:
    """Gain and phase margins of an open-loop response `L(jω)` (Ogata §7-6).

    - **Phase margin** is read at the *gain* crossover, where `|L| = 1`:
      `PM = 180° + ∠L`. How much extra lag the loop tolerates before `∠L`
      reaches -180° with the gain still at unity.
    - **Gain margin** is read at the *phase* crossover, where `∠L = -180°`:
      `GM = -20 log10 |L|` dB. How much extra gain it tolerates before `|L|`
      reaches 1 with the phase already inverted.

    Either is `None` when its crossover is not on the grid — a loop whose gain
    never reaches unity has no phase margin to report, and inventing one by
    extrapolating past the data would be worse than saying so. When a crossover
    happens more than once the *smallest* margin is returned, since that is the
    one that binds.
    """
    omega = np.asarray(omega, dtype=float)
    L = np.asarray(L, dtype=np.complex128)
    lg = np.log10(omega)
    mag_db = 20.0 * np.log10(np.maximum(np.abs(L), 1e-300))
    phase = np.degrees(np.unwrap(np.angle(L)))

    out: dict[str, float | None] = {
        "gain_margin_db": None, "phase_crossover": None,
        "phase_margin_deg": None, "gain_crossover": None,
    }

    # phase margin, at |L| = 1
    best = None
    for lw in _cross(lg, mag_db, 0.0):
        pm = 180.0 + float(np.interp(lw, lg, phase))
        if best is None or abs(pm) < abs(best[0]):
            best = (pm, 10.0**lw)
    if best:
        out["phase_margin_deg"], out["gain_crossover"] = best[0], best[1]

    # gain margin, at angle(L) = -180 deg (or any odd multiple, after unwrapping)
    best = None
    lo, hi = float(np.min(phase)), float(np.max(phase))
    k = int(np.floor((lo + 180.0) / 360.0))
    while (level := -180.0 + 360.0 * k) <= hi:
        for lw in _cross(lg, phase, level):
            gm = -float(np.interp(lw, lg, mag_db))
            if best is None or abs(gm) < abs(best[0]):
                best = (gm, 10.0**lw)
        k += 1
    if best:
        out["gain_margin_db"], out["phase_crossover"] = best[0], best[1]
    return out


def _track(previous: NDArray[np.complex128], current: NDArray[np.complex128]
           ) -> NDArray[np.complex128]:
    """Reorder `current` so each entry continues the nearest entry of `previous`.

    `eigvals` returns roots in no particular order, so joining consecutive gains
    index-by-index draws a branch that teleports between poles. Greedy
    nearest-neighbour matching is enough here: the gain steps are fine relative
    to how far a root moves, and the ambiguous case — two branches meeting at a
    breakaway point — is one where either assignment draws the same picture.
    """
    out = np.empty_like(current)
    taken = np.zeros(current.size, dtype=bool)
    for i, p in enumerate(previous):
        d = np.abs(current - p)
        d[taken] = np.inf
        j = int(np.argmin(d))
        out[i] = current[j]
        taken[j] = True
    return out


def root_locus(
    A: ArrayLike, B: ArrayLike, C: ArrayLike, D: ArrayLike, gains: ArrayLike
) -> tuple[NDArray[np.float64], NDArray[np.complex128]]:
    """Closed-loop poles of `1 + k L(s) = 0` as `k` sweeps (Ogata §6).

    Takes `L` as the state-space `(A, B, C, D)` that `loop_transfer` returns, so
    the poles come from an eigenvalue solve rather than from rooting a
    polynomial — no characteristic polynomial is ever formed, and none of its
    conditioning problems arise. Closing gain `k` around `L` gives

        A_cl(k) = A - (k / (1 + k D)) B C

    for a SISO loop. Returns `(gains, roots)` with `roots` shaped
    `(len(gains), n_states)`, each **column** a continuous branch.

    `k = 1` reproduces the actual closed loop and `k = 0` the open-loop poles;
    both are asserted in the tests, since a root locus that does not pass through
    the design point is drawing some other system.
    """
    A = np.atleast_2d(np.asarray(A, dtype=float))
    n = A.shape[0]
    b = np.asarray(B, dtype=float).reshape(n)
    c = np.asarray(C, dtype=float).reshape(n)
    d = float(np.asarray(D, dtype=float).reshape(-1)[0])
    gains = np.asarray(gains, dtype=float)

    roots = np.empty((gains.size, n), dtype=np.complex128)
    previous: NDArray[np.complex128] | None = None
    for i, k in enumerate(gains):
        denom = 1.0 + k * d
        if abs(denom) < 1e-12:
            # k D = -1: the algebraic loop is singular and there is no finite
            # closed loop at this gain. Leave a gap rather than draw through it.
            roots[i] = np.nan
            previous = None
            continue
        ev = np.asarray(np.linalg.eigvals(A - (k / denom) * np.outer(b, c)),
                        dtype=np.complex128)
        roots[i] = ev if previous is None else _track(previous, ev)
        previous = roots[i]
    return gains, roots


def gain_sweep(k_max: float = 100.0, n: int = 200) -> NDArray[np.float64]:
    """Gains for a root locus: 0, then log-spaced either side of the design gain.

    Log-spaced because a locus moves fast near `k = 0` and slowly afterwards, and
    `k = 1` is forced in so the drawn branch passes exactly through the loop as
    it is actually built.
    """
    lo = np.logspace(-3, 0, n // 2, endpoint=False)
    hi = np.logspace(0, np.log10(max(k_max, 1.0 + 1e-9)), n - n // 2)
    return np.unique(np.concatenate([[0.0], lo, [1.0], hi]))
