"""End-to-end: mock → events → I0 → C,R,G0 → holdout → artifacts + reconstruct plot."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .holdout import evaluate_reconstruct, holdout_metrics
from .i0 import fit_i0, save_i0
from .mock_data import save_mock
from .prep import add_markouts, build_events
from .tim1 import (
    choose_L,
    estimate_c_r,
    g_from_G0,
    invert_tim1,
    invert_tim1_differential,
    save_series,
)


ROOT = Path(__file__).resolve().parents[1]


def run(
    data_dir: Path | None = None,
    art_dir: Path | None = None,
    units: str = "bps",
    preferred_L: int = 80,
    ridge: float = 1e-8,
    mock_kwargs: dict | None = None,
) -> dict:
    data_dir = Path(data_dir or ROOT / "data")
    art_dir = Path(art_dir or ROOT / "artifacts")
    data_dir.mkdir(parents=True, exist_ok=True)
    art_dir.mkdir(parents=True, exist_ok=True)

    tp, qp, planted = save_mock(str(data_dir), **(mock_kwargs or {}))
    trades = pd.read_parquet(tp)
    quotes = pd.read_parquet(qp)

    events = build_events(trades, quotes)
    events = add_markouts(events, quotes)
    events_path = art_dir / "events.parquet"
    events.to_parquet(events_path, index=False)
    events.to_csv(art_dir / "events.csv", index=False)

    i0 = fit_i0(events, y_col="y_1.0s")
    save_i0(i0, art_dir / "i0_fit.json")

    N = len(events)
    L = choose_L(N, preferred=preferred_L)
    C, R = estimate_c_r(events, L=L, units=units)
    save_series(art_dir / "C.csv", np.arange(0, L + 1), C, "C")
    save_series(art_dir / "R.csv", np.arange(1, L + 1), R, "R")

    # Always compute BOTH paths; record both (E)
    G0_mat, A, R_hat_mat = invert_tim1(C, R, ridge=ridge)
    G0_diff, Gamma, Sigma = invert_tim1_differential(events, C, L, units=units)
    save_series(art_dir / "G0_matrix.csv", np.arange(1, L + 1), G0_mat, "G0")
    save_series(art_dir / "G0_differential.csv", np.arange(1, L + 1), G0_diff, "G0")

    # Score both solvers on the same holdout; primary = argmax holdout R²
    holdout = holdout_metrics(events, L=L, units=units, ridge=ridge, art_dir=art_dir)
    primary = holdout["primary_by_holdout_r2"]
    warning = bool(holdout["G0_solver_warning"])
    if primary == "matrix":
        G0, R_hat = G0_mat, R_hat_mat
    else:
        G0 = G0_diff
        R_hat = A @ G0

    g = g_from_G0(G0)
    save_series(art_dir / "G0.csv", np.arange(1, L + 1), G0, "G0")
    save_series(art_dir / "g.csv", np.arange(1, L + 1), g, "g")
    save_series(art_dir / "R_hat.csv", np.arange(1, L + 1), R_hat, "R_hat")

    # Reconstruct plot
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes[0, 0].plot(np.arange(1, L + 1), R, label="R empir")
    axes[0, 0].plot(np.arange(1, L + 1), R_hat, "--", label="R= A G0")
    axes[0, 0].set_title(f"Response reconstruct ({units})")
    axes[0, 0].legend()
    axes[0, 1].plot(np.arange(0, L + 1), C)
    axes[0, 1].set_title("Sign ACF C")
    axes[1, 0].plot(np.arange(1, L + 1), G0, label="G0 primary")
    axes[1, 0].plot(np.arange(1, L + 1), G0_diff, "--", alpha=0.7, label="G0 diff")
    axes[1, 0].set_title("Bare G0")
    axes[1, 0].legend()
    axes[1, 1].plot(np.arange(1, L + 1), g)
    axes[1, 1].axhline(1.0, color="k", lw=0.5)
    axes[1, 1].set_title("g(ℓ)=G0(ℓ)/G0(1)")
    fig.suptitle(f"1347.HK mock TIM1  N={N} L={L} primary={primary}")
    fig.tight_layout()
    fig.savefig(art_dir / "reconstruct.png", dpi=120)
    plt.close(fig)

    eval_full = evaluate_reconstruct(R, R_hat)
    meta = {
        "sym": "1347.HK",
        "N_events": N,
        "L": L,
        "units": units,
        "mid_convention": "mid just before trade (Lee-Ready vs last quote t_quote < t_trade)",
        "inside_spread": "dropped",
        "G0_solver": primary,
        "G0_solver_selection": "argmax holdout R2 (matrix vs differential on same split)",
        "G0_solver_warning": warning,
        "holdout_r2_matrix": holdout["matrix"]["holdout"]["r2"],
        "holdout_r2_differential": holdout["differential"]["holdout"]["r2"],
        "ridge": ridge,
        "G0_1": float(G0[0]),
        "G0_matrix_1": float(G0_mat[0]),
        "G0_differential_1": float(G0_diff[0]),
        "corr_G0_matrix_vs_differential": float(np.corrcoef(G0_mat, G0_diff)[0, 1]),
        "g_1": float(g[0]),
        # §8.3 in-sample reconstruct metrics (top-level)
        "sse": eval_full["sse"],
        "r2": eval_full["r2"],
        "rmse": eval_full["rmse"],
        "R_vs_Rhat_corr": eval_full["R_vs_Rhat_corr"],
        "holdout": holdout,
        "i0_a": i0["a"],
        "i0_b": i0["b"],
        "i0_stat_used": i0["stat_used"],
        "planted_kernel": planted,
        "notes": "One-day mock — fits are noisy; do not treat b/β as production truth.",
    }
    (art_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    return meta
