"""Unit tests for response metrics, including the transient guard."""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.metrics import reduction, steady_state
from fuzzy.sim import Log


def sine_log(t_max: float, dt: float = 0.001, amp: float = 2.0) -> Log:
    """Unit-period sine, so a whole-second window holds an exact integer of cycles
    and RMS is analytically `amp / sqrt(2)`."""
    t = np.arange(0.0, t_max + dt / 2, dt)
    return Log(t=t, signals={"s.y": amp * np.sin(2.0 * np.pi * t)})


def test_peak_and_rms_of_a_sine():
    m = steady_state(sine_log(10.0), "s.y", window=4.0)
    assert m["peak"] == pytest.approx(2.0, rel=1e-3)
    assert m["rms"] == pytest.approx(2.0 / np.sqrt(2.0), rel=1e-3)
    assert m["mean"] == pytest.approx(0.0, abs=1e-2)


def test_no_warning_when_window_is_genuinely_settled():
    # 40 s run, 4 s window, tau = 5 s -> 36 s of settling vs 20 s required
    with warnings_as_errors():
        steady_state(sine_log(40.0), "s.y", window=4.0, tau=5.0)


def test_warns_when_window_is_still_transient():
    """The exercise-2 configuration: t_max=12, window=4, tau=5."""
    with pytest.warns(UserWarning, match="not steady state"):
        steady_state(sine_log(12.0), "s.y", window=4.0, tau=5.0)


def test_warning_names_the_required_horizon():
    with pytest.warns(UserWarning, match=r"at least 24\.0 s"):
        steady_state(sine_log(12.0), "s.y", window=4.0, tau=5.0)


def test_window_longer_than_run_raises():
    with pytest.raises(ValueError, match="shorter than the run"):
        steady_state(sine_log(2.0), "s.y", window=5.0)


def test_vector_signal_requires_index():
    t = np.linspace(0.0, 10.0, 1001)
    log = Log(t=t, signals={"p.y": np.column_stack([np.sin(t), np.cos(t)])})
    with pytest.raises(ValueError, match="vector-valued"):
        steady_state(log, "p.y", window=2.0)
    m = steady_state(log, "p.y", window=2.0, index=1)
    assert m["peak"] <= 1.0 + 1e-12


def test_unknown_signal_lists_available_keys():
    with pytest.raises(KeyError, match="s.y"):
        steady_state(sine_log(10.0), "nope", window=1.0)


def test_reduction():
    assert reduction(0.25, 0.0742) == pytest.approx(0.7032, rel=1e-3)
    with pytest.raises(ValueError):
        reduction(0.0, 1.0)


class warnings_as_errors:
    """Context manager asserting no warning is raised."""

    def __enter__(self):
        import warnings

        self._cm = warnings.catch_warnings()
        self._cm.__enter__()
        warnings.simplefilter("error")
        return self

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)
