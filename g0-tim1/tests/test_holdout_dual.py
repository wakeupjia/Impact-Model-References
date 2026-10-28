"""Dual-solver holdout: primary by holdout R²."""

from __future__ import annotations

from g0_tim1.holdout import holdout_metrics
from g0_tim1.synth import make_events


def test_dual_solver_holdout_has_both_paths():
    ev, _ = make_events(N=2500, L_true=30, seed=5)
    m = holdout_metrics(ev, L=30, units="price")
    assert "matrix" in m and "differential" in m
    assert m["primary_by_holdout_r2"] in ("matrix", "differential")
    assert "max_abs_e" in m["holdout"]
    assert "rmse_over_std_R" in m["holdout"]
    assert m["matrix"]["holdout"]["r2"] == m["matrix"]["holdout"]["r2"]  # finite
