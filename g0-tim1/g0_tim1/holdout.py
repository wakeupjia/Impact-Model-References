"""Train/holdout split + OLS-style AG0=R eval (guide §8)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .tim1 import build_A, estimate_c_r, invert_tim1, invert_tim1_differential


def split_holdout(events: pd.DataFrame, train_frac: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_train = int(len(events) * train_frac)
    return events.iloc[:n_train], events.iloc[n_train:]


def evaluate_reconstruct(R: np.ndarray, R_hat: np.ndarray) -> dict:
    """§8.3: score how well AĜ0 matches empirical R (not mid-move prediction)."""
    R = np.asarray(R, dtype=float)
    R_hat = np.asarray(R_hat, dtype=float)
    e = R - R_hat
    L = len(R)
    sse = float(e @ e)
    R_c = R - R.mean()
    denom = float(R_c @ R_c)
    r2 = float(1.0 - sse / denom) if denom > 0 else float("nan")
    rmse = float(np.sqrt(sse / L)) if L > 0 else float("nan")
    std_R = float(np.std(R))
    corr = (
        float(np.corrcoef(R, R_hat)[0, 1])
        if np.std(R_hat) > 0 and std_R > 0
        else float("nan")
    )
    return {
        "sse": sse,
        "r2": r2,
        "rmse": rmse,
        "R_vs_Rhat_corr": corr,
        "max_abs_e": float(np.max(np.abs(e))) if L else float("nan"),
        "rmse_over_std_R": float(rmse / std_R) if std_R > 0 else float("nan"),
        "L": int(L),
    }


def reconstruct_metrics(R: np.ndarray, R_hat: np.ndarray) -> dict:
    return evaluate_reconstruct(R, R_hat)


def _score_path(
    events_train: pd.DataFrame,
    events_hold: pd.DataFrame,
    L: int,
    units: str,
    ridge: float,
    solver: str,
) -> tuple[dict, dict, np.ndarray, np.ndarray, np.ndarray]:
    """Fit Ĝ0 on train with solver; score train in-sample + A_test@Ĝ0_train vs R_test."""
    C_tr, R_tr = estimate_c_r(events_train, L=L, units=units)
    if solver == "matrix":
        G0_tr, _, R_hat_tr = invert_tim1(C_tr, R_tr, ridge=ridge)
    elif solver == "differential":
        G0_tr, _, _ = invert_tim1_differential(events_train, C_tr, L, units=units)
        A_tr = build_A(C_tr, L)
        R_hat_tr = A_tr @ G0_tr
    else:
        raise ValueError(solver)

    C_te, R_te = estimate_c_r(events_hold, L=L, units=units)
    A_te = build_A(C_te, L)
    R_hat_te = A_te @ G0_tr

    G0_te_mat, _, _ = invert_tim1(C_te, R_te, ridge=ridge)
    if solver == "differential":
        G0_te, _, _ = invert_tim1_differential(events_hold, C_te, L, units=units)
    else:
        G0_te = G0_te_mat

    train_m = evaluate_reconstruct(R_tr, R_hat_tr)
    hold_m = evaluate_reconstruct(R_te, R_hat_te)
    # drop bulky residuals from train metrics kept in JSON (keep on holdout only)
    train_m_slim = {k: v for k, v in train_m.items() if k != "residuals"}
    hold_m_slim = {k: v for k, v in hold_m.items() if k != "residuals"}
    return train_m_slim, hold_m_slim, G0_tr, G0_te, hold_m["residuals"] if False else np.asarray(hold_m.pop("residuals") if "residuals" in hold_m else hold_m.get("residuals", []))


def holdout_metrics(
    events: pd.DataFrame,
    L: int,
    units: str = "bps",
    ridge: float = 1e-8,
    train_frac: float = 0.7,
    art_dir: Path | None = None,
) -> dict:
    """Score matrix AND differential on the same holdout; pick primary by holdout R²."""
    train, hold = split_holdout(events, train_frac=train_frac)
    if len(hold) <= L + 2:
        raise ValueError(f"holdout N={len(hold)} too small for L={L}")

    paths = {}
    residuals = {}
    for solver in ("matrix", "differential"):
        C_tr, R_tr = estimate_c_r(train, L=L, units=units)
        if solver == "matrix":
            G0_tr, _, R_hat_tr = invert_tim1(C_tr, R_tr, ridge=ridge)
        else:
            G0_tr, _, _ = invert_tim1_differential(train, C_tr, L, units=units)
            R_hat_tr = build_A(C_tr, L) @ G0_tr

        C_te, R_te = estimate_c_r(hold, L=L, units=units)
        A_te = build_A(C_te, L)
        R_hat_te = A_te @ G0_tr

        if solver == "matrix":
            G0_te, _, _ = invert_tim1(C_te, R_te, ridge=ridge)
        else:
            G0_te, _, _ = invert_tim1_differential(hold, C_te, L, units=units)

        train_m = evaluate_reconstruct(R_tr, R_hat_tr)
        hold_m = evaluate_reconstruct(R_te, R_hat_te)
        residuals[solver] = R_te - R_hat_te
        paths[solver] = {
            "G0_train_1": float(G0_tr[0]),
            "G0_test_1": float(G0_te[0]),
            "G0_l2_diff": float(np.linalg.norm(G0_tr - G0_te)),
            "train": train_m,
            "holdout": hold_m,
        }

    # Primary by holdout R² (tie → matrix); still flag if G0(1)<=0 on winner
    r2_m = paths["matrix"]["holdout"]["r2"]
    r2_d = paths["differential"]["holdout"]["r2"]
    if r2_d > r2_m:
        primary = "differential"
    else:
        primary = "matrix"
    warning = paths[primary]["G0_train_1"] <= 0

    # lag-wise residual plot for primary
    e_pri = residuals[primary]
    lags = np.arange(1, L + 1)
    if art_dir is not None:
        art_dir = Path(art_dir)
        art_dir.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 3.6))
        ax.axhline(0.0, color="k", lw=0.6)
        ax.plot(lags, e_pri, color="#4269d0", lw=1.5, label=f"e = R − AĜ0 ({primary})")
        ax.set_xlabel("lag ℓ (trades)")
        ax.set_ylabel("residual")
        ax.set_title(
            f"Holdout lag-wise residuals · max|e|={np.max(np.abs(e_pri)):.4g} · "
            f"RMSE/std(R)={paths[primary]['holdout']['rmse_over_std_R']:.4g}"
        )
        ax.grid(True, alpha=0.25, lw=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(art_dir / "holdout_residuals.png", dpi=120)
        plt.close(fig)
        # also dump residual series
        pd.DataFrame({"lag": lags, "e": e_pri}).to_csv(art_dir / "holdout_residuals.csv", index=False)

    winner = paths[primary]
    return {
        "n_train": int(len(train)),
        "n_holdout": int(len(hold)),
        "train_frac": float(train_frac),
        "L": L,
        "primary_by_holdout_r2": primary,
        "G0_solver_warning": warning,
        "matrix": paths["matrix"],
        "differential": paths["differential"],
        "note": "Both solvers scored on same holdout (A_test @ G0_train vs R_test); primary = argmax holdout R².",
        # flat winner fields (back-compat)
        "G0_train_1": winner["G0_train_1"],
        "G0_test_1": winner["G0_test_1"],
        "G0_l2_diff": winner["G0_l2_diff"],
        "train": winner["train"],
        "holdout": winner["holdout"],
        "sse": winner["holdout"]["sse"],
        "r2": winner["holdout"]["r2"],
        "rmse": winner["holdout"]["rmse"],
        "R_vs_Rhat_corr": winner["holdout"]["R_vs_Rhat_corr"],
        "max_abs_e": winner["holdout"]["max_abs_e"],
        "rmse_over_std_R": winner["holdout"]["rmse_over_std_R"],
        "corr_train_R_vs_Rhat": winner["train"]["R_vs_Rhat_corr"],
        "corr_holdout_R_vs_Rhat": winner["holdout"]["R_vs_Rhat_corr"],
        "residual_plot": "artifacts/holdout_residuals.png" if art_dir is not None else None,
    }
