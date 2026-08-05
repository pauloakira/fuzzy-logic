"""Linear-analysis primitives checked against closed-form SDOF results.

The plant `m x'' + c x' + k x = u` with state `[x, x']` has
`A = [[0, 1], [-k/m, -c/m]]`, `B = [[0], [1/m]]`, `C = I`, `D = 0`. Its
transfer functions are `X/U = 1/(m s^2 + c s + k)` (no finite zero) and
`X'/U = s/(m s^2 + c s + k)` (one zero at the origin), and the DC gain of the
position channel is `1/k`. These are the facts the tests pin down.
"""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.analysis import (
    faddeev_leverrier,
    frequency_grid,
    frequency_response,
    margins,
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


def test_the_grid_does_not_gain_a_decade_from_rounding():
    """A numerical Jacobian returns a pole of 1 as 0.999999999995, whose log10 is
    a hair negative; `floor` then reaches a decade further than for the exact
    model, and the same system plots over two different ranges."""
    exact = frequency_grid([1.0 + 0j], decades=2.0, n=50)
    nudged = frequency_grid([0.999999999995 + 0j], decades=2.0, n=50)
    assert nudged[0] == np.float64(exact[0])
    assert nudged[-1] == np.float64(exact[-1])


# ----- stability margins ----------------------------------------------------------


def test_margins_of_the_textbook_third_order_loop():
    """`L = 1/(s(s+1)(s+2))`, whose margins are worked out in every text: the
    phase crosses -180 deg at `sqrt(2)`, where `|L| = 1/6`."""
    w = np.logspace(-3, 3, 40001)
    L = 1.0 / ((1j * w) * (1j * w + 1) * (1j * w + 2))
    m = margins(w, L)
    assert m["phase_crossover"] == pytest.approx(np.sqrt(2), rel=1e-4)
    assert m["gain_margin_db"] == pytest.approx(20 * np.log10(6.0), rel=1e-4)
    assert m["phase_margin_deg"] == pytest.approx(53.41, abs=0.05)
    assert m["gain_crossover"] == pytest.approx(0.4457, abs=1e-3)


def test_a_margin_with_no_crossover_is_none_not_extrapolated():
    """A second-order loop's phase approaches -180 deg without reaching it, so it
    has no gain margin. Inventing one by running off the end of the grid would be
    worse than saying there is none."""
    w = np.logspace(-2, 2, 4001)
    L = 25.0 / ((1j * w) ** 2 + 0.4 * (1j * w) + 100.0)
    m = margins(w, L)
    assert m["gain_margin_db"] is None and m["phase_crossover"] is None
    assert m["phase_margin_deg"] == pytest.approx(10.29, abs=0.05)


def test_the_binding_margin_is_the_one_reported():
    """Several crossings are possible; the smallest is the one that constrains."""
    w = np.logspace(-3, 3, 40001)
    L = 1.0 / ((1j * w) * (1j * w + 1) * (1j * w + 2))
    m = margins(w, L)
    assert 0.0 < m["gain_margin_db"] < 20.0
