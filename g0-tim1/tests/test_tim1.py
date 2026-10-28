"""Unit tests: synthetic TIM1 recovery (exact generative) + g(1) + age buffer."""

from __future__ import annotations

import numpy as np
import pytest

from g0_tim1.i0 import fit_i0
from g0_tim1.state import AgeBuffer
from g0_tim1.synth import make_events, synthetic_recovery
from g0_tim1.tim1 import build_A, estimate_c_r, g_from_G0, invert_tim1


def test_g1_equals_one():
    G0 = np.array([2.0, 1.5, 1.0, 0.7])
    g = g_from_G0(G0)
    assert g[0] == pytest.approx(1.0)


def test_build_A_shape():
    C = np.array([1.0, 0.4, 0.2, 0.1])
    A = build_A(C, L=3)
    assert A.shape == (3, 3)
    # spot-check the Taranto form: A_11 = C(0) - C(1); A_12 = C(1) - C(2)
    assert A[0, 0] == pytest.approx(1.0 - 0.4)
    assert A[0, 1] == pytest.approx(0.4 - 0.2)


def test_synth_generative_matches_kernel():
    """mid[n] must equal m0 + Σ_{j<n} G0(n-j) ε_j exactly (noise=0).

    The generative kernel is the permanent-tail one (g1·ℓ^-γ+g∞ at ALL lags);
    true_G0 returned is just its first L_true values.
    """
    g1, gamma, g_inf = 0.002, 0.4, 0.0005
    ev, true_G0 = make_events(N=500, L_true=20, g1=g1, gamma=gamma, g_inf=g_inf, noise=0.0, seed=1)
    eps = ev["eps"].to_numpy(dtype=float)
    mid = ev["mid_before"].to_numpy()
    for n in (1, 10, 50, 200):
        expected = 100.0 + sum((g1 * (n - j) ** -gamma + g_inf) * eps[j] for j in range(n))
        assert mid[n] == pytest.approx(expected, abs=1e-9)


def test_synthetic_tim1_recovers_known_G0():
    """Researchy bar: G0(1)>0, corr(true,Ĝ0)>0.7, corr(R,AĜ0)>0.9."""
    res = synthetic_recovery(N=4000, L_true=40, noise=5e-4, seed=0)
    assert res["g0hat_1"] > 0
    assert res["corr_true_vs_g0hat"] > 0.7
    assert res["corr_R_vs_Rhat"] > 0.9


def test_synthetic_recovery_noiseless():
    """Noiseless generative: full-kernel corr bounded by C sampling noise (~0.95);
    the economically meaningful early lags must recover almost exactly."""
    res = synthetic_recovery(N=3000, L_true=40, noise=0.0, seed=3)
    assert res["corr_true_vs_g0hat"] > 0.9
    early_corr = np.corrcoef(res["true_G0"][:10], res["G0_hat"][:10])[0, 1]
    assert early_corr > 0.99
    assert np.max(np.abs(res["G0_hat"][:10] - res["true_G0"][:10])) < 1e-4
    assert res["corr_R_vs_Rhat"] > 0.99


def test_age_buffer_matches_g():
    G0 = np.array([2.0, 1.6, 1.2, 0.9, 0.6])
    fit = {"a": 1.0, "b": 0.0}  # I0=1 bps for any q
    buf = AgeBuffer(G0=G0, i0_fit=fit)
    buf.on_own_take(q=1000)
    assert buf.S() == pytest.approx(1.0 * 1.0)  # age=1 → g=1
    buf.on_public_trade(1)
    assert buf.takes[0].age == 2
    assert buf.S() == pytest.approx(1.0 * (1.6 / 2.0))
    assert buf.S(extra_lag=2) == pytest.approx(1.0 * (0.9 / 2.0))


def test_age_buffer_drops_expired_takes():
    G0 = np.array([2.0, 1.6])
    buf = AgeBuffer(G0=G0, i0_fit={"a": 1.0, "b": 0.0})
    buf.on_own_take(q=100)
    buf.on_public_trade(5)  # age 6 > L_keep=2
    assert buf.takes == []
    assert buf.S() == 0.0


def test_i0_fit_reports_stat_and_caveat():
    import pandas as pd

    rng = np.random.default_rng(7)
    n = 400
    q = np.exp(rng.normal(7.5, 0.5, size=n))
    df = pd.DataFrame(
        {"q": q, "y_1.0s": 0.5 * q ** 0.3 + rng.normal(0, 0.05, n)}
    )
    fit = fit_i0(df, y_col="y_1.0s")
    assert fit["stat_used"] in ("median", "mean")
    assert "not trusted" in fit["caveat"]
    assert 0.0 < fit["b"] < 1.0
