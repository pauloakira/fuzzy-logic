"""Linear-analysis primitives checked against closed-form SDOF results.

The plant `m x'' + c x' + k x = u` with state `[x, x']` has
`A = [[0, 1], [-k/m, -c/m]]`, `B = [[0], [1/m]]`, `C = I`, `D = 0`. Its
transfer functions are `X/U = 1/(m s^2 + c s + k)` (no finite zero) and
`X'/U = s/(m s^2 + c s + k)` (one zero at the origin), and the DC gain of the
position channel is `1/k`. These are the facts the tests pin down.
"""

from __future__ import annotations

import numpy as np

from fuzzy.analysis import (
    faddeev_leverrier,
    frequency_grid,
    frequency_response,
    poles,
    zeros,
)
from fuzzy.blocks import sdof_plant

M, C_DAMP, K = 1.0, 0.4, 4.0
PLANT = sdof_plant(m=M, c=C_DAMP, k=K)


def test_poles_match_the_characteristic_roots():
    got = np.sort_complex(poles(PLANT.A))
    want = np.sort_complex(np.roots([M, C_DAMP, K]))
    assert np.allclose(got, want)


def test_faddeev_leverrier_recovers_the_characteristic_polynomial():
    p, Bs = faddeev_leverrier(PLANT.A)
    # det(sI - A) = s^2 + (c/m) s + k/m
    assert np.allclose(p, [1.0, C_DAMP / M, K / M])
    assert len(Bs) == PLANT.A.shape[0]
    assert np.allclose(Bs[0], np.eye(2))  # B_0 = I


def test_position_channel_has_no_finite_zero():
    z = zeros(PLANT.A, PLANT.B[:, 0], PLANT.C[0], PLANT.D[0, 0])
    assert z.size == 0


def test_velocity_channel_has_a_single_zero_at_the_origin():
    z = zeros(PLANT.A, PLANT.B[:, 0], PLANT.C[1], PLANT.D[1, 0])
    assert z.size == 1
    assert abs(z[0]) < 1e-9


def test_frequency_response_shape_and_dc_gain():
    omega = np.logspace(-3, 1, 50)
    H = frequency_response(PLANT.A, PLANT.B, PLANT.C, PLANT.D, omega)
    assert H.shape == (50, 2, 1)  # (n_omega, n_out, n_in)
    dc = frequency_response(PLANT.A, PLANT.B, PLANT.C, PLANT.D, [1e-6])
    assert np.isclose(abs(dc[0, 0, 0]), 1.0 / K, rtol=1e-3)  # position DC gain
    assert abs(dc[0, 1, 0]) < 1e-4                            # velocity DC gain ~ 0


def test_frequency_grid_brackets_the_natural_frequency():
    wn = np.sqrt(K / M)
    grid = frequency_grid(poles(PLANT.A), decades=2.0, n=200)
    assert grid[0] < wn < grid[-1]
    assert grid[0] <= wn / 100 and grid[-1] >= wn * 100


def test_frequency_grid_falls_back_without_finite_criticals():
    grid = frequency_grid([0.0, 0.0], n=10)
    assert np.isclose(grid[0], 1e-2) and np.isclose(grid[-1], 1e2)
