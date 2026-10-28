"""§8.5: evaluate_reconstruct on exact R = A G0 → r2≈1, rmse≈0."""

from __future__ import annotations

import numpy as np

from g0_tim1.holdout import evaluate_reconstruct
from g0_tim1.synth import synthetic_recovery
from g0_tim1.tim1 import build_A


def test_evaluate_reconstruct_exact():
    C = np.array([1.0, 0.5, 0.25, 0.1, 0.05])
    L = 4
    A = build_A(C, L)
    G0 = np.array([2.0, 1.5, 1.0, 0.7])
    R = A @ G0
    m = evaluate_reconstruct(R, A @ G0)
    assert m["r2"] == 1.0 or abs(m["r2"] - 1.0) < 1e-12
    assert m["rmse"] < 1e-12
    assert m["sse"] < 1e-24
    assert abs(m["R_vs_Rhat_corr"] - 1.0) < 1e-12


def test_synthetic_reports_g0_rmse_and_recon():
    res = synthetic_recovery(N=2000, L_true=30, noise=0.0, seed=2)
    assert "G0_recovery_rmse" in res
    assert res["r2"] > 0.99
    assert res["rmse"] >= 0.0
    assert res["G0_recovery_rmse"] >= 0.0
