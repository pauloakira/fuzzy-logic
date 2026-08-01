"""Linear design tools: LQR gains and observer gains.

These produce the `K` and `L` matrices that `StateFeedback` and `Observer`
consume. Both reduce to solving an algebraic Riccati equation, done here with
the Hamiltonian eigenvector method so the repo keeps no dependency beyond NumPy
(SciPy's `solve_continuous_are` is the production answer; this is the
transparent one, and `are_residual` exists to prove it agrees).

Why this matters for the fuzzy work: LQR is the *optimal* linear state-feedback
law for a given cost, so it is a far more defensible benchmark than one
hand-tuned PID. And the observer is what removes the exercise's biggest
idealisation — the fuzzy controller currently receives perfect velocity, which
no real accelerometer provides.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


class RiccatiError(RuntimeError):
    """The Riccati equation could not be solved — usually an uncontrollable pair."""


def _as2d(m: ArrayLike) -> NDArray[np.float64]:
    return np.atleast_2d(np.asarray(m, dtype=float))


def solve_care(
    A: ArrayLike, B: ArrayLike, Q: ArrayLike, R: ArrayLike
) -> NDArray[np.float64]:
    """Solve `A'P + PA - PBR^-1B'P + Q = 0` for the stabilising `P`.

    Hamiltonian method: the eigenvectors of

        H = [[A, -B R^-1 B'], [-Q, -A']]

    belonging to the stable (negative-real-part) eigenvalues span an invariant
    subspace `[X; Y]`, and `P = Y X^-1` is the stabilising solution.
    """
    A, B, Q, R = _as2d(A), _as2d(B), _as2d(Q), _as2d(R)
    n = A.shape[0]
    if A.shape != (n, n) or Q.shape != (n, n):
        raise RiccatiError("`A` and `Q` must be square and the same size")
    if B.shape[0] != n:
        raise RiccatiError("`B` must have as many rows as `A`")

    try:
        Rinv = np.linalg.inv(R)
    except np.linalg.LinAlgError as exc:
        raise RiccatiError("`R` must be invertible (and positive definite)") from exc

    H = np.block([[A, -B @ Rinv @ B.T], [-Q, -A.T]])
    values, vectors = np.linalg.eig(H)

    stable = np.argsort(values.real)[:n]
    if np.any(values.real[stable] >= 0):
        raise RiccatiError(
            "no stable invariant subspace: the (A, B) pair is probably not "
            "stabilisable, or Q is not positive semidefinite"
        )

    X, Y = vectors[:n, stable], vectors[n:, stable]
    try:
        P = Y @ np.linalg.inv(X)
    except np.linalg.LinAlgError as exc:
        raise RiccatiError("degenerate invariant subspace") from exc

    P = np.real((P + P.conj().T) / 2.0)  # symmetrise away round-off
    return P


def are_residual(
    A: ArrayLike, B: ArrayLike, Q: ArrayLike, R: ArrayLike, P: ArrayLike
) -> float:
    """Max absolute residual of the Riccati equation — a direct correctness check."""
    A, B, Q, R, P = _as2d(A), _as2d(B), _as2d(Q), _as2d(R), _as2d(P)
    res = A.T @ P + P @ A - P @ B @ np.linalg.inv(R) @ B.T @ P + Q
    return float(np.max(np.abs(res)))


def lqr(
    A: ArrayLike, B: ArrayLike, Q: ArrayLike, R: ArrayLike
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.complex128]]:
    """Optimal state feedback `u = -K x` minimising `int x'Qx + u'Ru dt`.

    Returns `(K, P, closed_loop_eigenvalues)`.
    """
    A, B = _as2d(A), _as2d(B)
    P = solve_care(A, B, Q, R)
    K = np.linalg.inv(_as2d(R)) @ B.T @ P
    # eigvals is float-or-complex depending on input; the caller is promised
    # complex, since a real matrix's spectrum generally is.
    return K, P, np.asarray(np.linalg.eigvals(A - B @ K), dtype=np.complex128)


def observer_gain(
    A: ArrayLike, C: ArrayLike, Qn: ArrayLike, Rn: ArrayLike
) -> tuple[NDArray[np.float64], NDArray[np.complex128]]:
    """Steady-state Kalman / Luenberger gain `L` for `x̂' = Ax̂ + Bu + L(y - Cx̂)`.

    Dual of the LQR problem: solve the Riccati equation for `(A', C')`, which is
    why no separate solver is needed. `Qn` is process-noise covariance, `Rn`
    measurement-noise covariance; raising `Rn` trusts the model over the sensor.

    Returns `(L, observer_eigenvalues)`.
    """
    A, C = _as2d(A), _as2d(C)
    Pf = solve_care(A.T, C.T, Qn, Rn)
    L = np.asarray(Pf @ C.T @ np.linalg.inv(_as2d(Rn)), dtype=np.float64)
    return L, np.asarray(np.linalg.eigvals(A - L @ C), dtype=np.complex128)
