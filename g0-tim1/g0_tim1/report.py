"""Metrics report: artifacts → TEST_REPORT.md + test_metrics.json + R_vs_Rhat.png.

Covers the researchy review checklist:
  1. synthetic TIM1 recovery of known G0 (corr(true,Ĝ0), Ĝ0(1)>0)
  2. corr(R, AĜ0) on the mock tape + plot
  3. g(1)=1 and age-buffer S unit check
  4. train/holdout (70/30) metrics
  5. explicit caveat: one-day mock → I0 b not trusted
  6. matrix vs differential G0 comparison
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .i0 import i0_bps
from .mock_data import planted_kernel_ticks
from .state import AgeBuffer
from .synth import synthetic_recovery
from .holdout import evaluate_reconstruct

ROOT = Path(__file__).resolve().parents[1]

# fixed two-series assignment (identity, never cycled): R empirical / R̂ = AĜ0
# pair validated (dataviz six-checks, light surface): CVD ΔE 36.7, both in lightness band, ≥3:1
COL_R = "#4269d0"
COL_RHAT = "#c77911"


def _load(art: Path, name: str, col: str) -> np.ndarray:
    return pd.read_csv(art / name)[col].to_numpy(dtype=float)


def _ok(flag: bool) -> str:
    return "PASS" if flag else "FAIL"


def generate_report(art_dir: Path | None = None) -> dict:
    art = Path(art_dir or ROOT / "artifacts")
    meta = json.loads((art / "run_meta.json").read_text())
    i0 = json.loads((art / "i0_fit.json").read_text())

    R = _load(art, "R.csv", "R")
    R_hat = _load(art, "R_hat.csv", "R_hat")
    G0 = _load(art, "G0.csv", "G0")
    G0_mat = _load(art, "G0_matrix.csv", "G0")
    G0_diff = _load(art, "G0_differential.csv", "G0")
    g = _load(art, "g.csv", "g")
    lags = np.arange(1, len(R) + 1)

    # -- 1. synthetic recovery of a known G0 --------------------------------
    syn = synthetic_recovery()
    _tg, _gh = syn["true_G0"], syn["G0_hat"]
    _Lc = min(len(_tg), len(_gh))
    _tgn = _tg[:_Lc] / _tg[0]
    _ghn = _gh[:_Lc] / _gh[0]
    syn_shape_corr = float(__import__("numpy").corrcoef(_tgn, _ghn)[0, 1])
    syn_pass = (
        syn["g0hat_1"] > 0.0
        and syn["corr_true_vs_g0hat"] > 0.7
        and syn["corr_R_vs_Rhat"] > 0.9
    )
    metrics = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "N_events": meta["N_events"],
        "L": meta["L"],
        "units": meta["units"],
        "primary_solver": meta["G0_solver"],
        "primary_solver_warning": meta["G0_solver_warning"],
        "checklist": {
            "1_synthetic_recovery": {
                "g0hat_1": syn["g0hat_1"],
                "g0hat_1_positive": bool(syn["g0hat_1"] > 0),
                "corr_true_G0_vs_G0hat": syn["corr_true_vs_g0hat"],
                "G0_recovery_rmse": syn["G0_recovery_rmse"],
                "shape_corr_normalized": syn_shape_corr,
                "corr_R_vs_Rhat_synth": syn["corr_R_vs_Rhat"],
                "bars": {"corr_true_G0_vs_G0hat": 0.7, "corr_R_vs_Rhat": 0.9},
                "pass": bool(syn_pass),
            },
            "2_mock_R_vs_Rhat": {
                "corr_R_vs_Rhat": meta["R_vs_Rhat_corr"],
                "plot": "artifacts/R_vs_Rhat.png",
                "planted_vs_G0hat_shape_corr": None,  # filled below
                "ols_eval": None,  # filled below from R, R_hat
            },
            "3_g1_and_age_buffer": {},
            "4_holdout": meta["holdout"],
            "5_caveats": {
                "one_day_mock_I0_b_not_trusted": True,
                "note": i0["caveat"],
            },
            "6_matrix_vs_differential": {
                "G0_matrix_1": meta["G0_matrix_1"],
                "G0_differential_1": meta["G0_differential_1"],
                "corr_matrix_vs_differential": meta["corr_G0_matrix_vs_differential"],
                "primary": meta["G0_solver"],
                "selection": meta.get("G0_solver_selection", ""),
                "holdout_r2_matrix": meta.get("holdout_r2_matrix"),
                "holdout_r2_differential": meta.get("holdout_r2_differential"),
                "warning": meta["G0_solver_warning"],
            },
        },
    }

    # planted-kernel shape check vs primary Ĝ0 (informational: quote noise +
    # Lee-Ready sign dilution shift the level; compare normalized shapes)
    planted = meta.get("planted_kernel", {})
    Lp = min(int(planted.get("L_planted", 0)), len(G0))
    if Lp >= 3:
        kp = planted_kernel_ticks(Lp, planted["g1_ticks"], planted["gamma"])
        gh = G0[:Lp] / G0[0]
        kpn = kp / kp[0]
        metrics["checklist"]["2_mock_R_vs_Rhat"]["planted_vs_G0hat_shape_corr"] = float(
            np.corrcoef(kpn, gh)[0, 1]
        )

    # OLS-style AG0=R eval on full mock (e=R-R̃)
    ols_full = evaluate_reconstruct(R, R_hat)
    metrics["checklist"]["2_mock_R_vs_Rhat"]["ols_eval"] = ols_full

    # -- 2. corr(R, A G0) + plot --------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(lags, R, color=COL_R, lw=2, label="R empirical")
    ax.plot(lags, R_hat, color=COL_RHAT, lw=2, ls="--", label="R̂ = A Ĝ0")
    ax.set_xlabel("lag ℓ (trades)")
    ax.set_ylabel(f"R({meta['units']})")
    ax.set_title(f"Mock 1347.HK: corr(R, AĜ0) = {meta['R_vs_Rhat_corr']:.3f}")
    ax.grid(True, alpha=0.25, lw=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(art / "R_vs_Rhat.png", dpi=120)
    plt.close(fig)

    # -- 3. g(1)=1 + age-buffer S unit check ---------------------------------
    g1_exact = bool(abs(g[0] - 1.0) < 1e-12)
    fit = {"a": i0["a"], "b": i0["b"]}
    buf = AgeBuffer(G0=G0, i0_fit=fit)
    q_take = 1000.0
    impact = float(i0_bps(q_take, fit))
    buf.on_own_take(q=q_take)
    s_age1 = buf.S()
    buf.on_public_trade(1)
    s_age2 = buf.S()
    buf.on_public_trade(len(G0))  # push take past L_keep → drops out
    s_expired = buf.S()
    age_ok = (
        abs(s_age1 - impact * g[0]) < 1e-9
        and abs(s_age2 - impact * g[1]) < 1e-9
        and s_expired == 0.0
    )
    metrics["checklist"]["3_g1_and_age_buffer"] = {
        "g_1": float(g[0]),
        "g_1_equals_one": g1_exact,
        "S_age1": float(s_age1),
        "S_age2": float(s_age2),
        "S_after_expiry": float(s_expired),
        "expected_S_age1": float(impact * g[0]),
        "expected_S_age2": float(impact * g[1]),
        "pass": bool(g1_exact and age_ok),
    }
    metrics["checklist"]["3_g1_and_age_buffer"]["pass"] = bool(g1_exact and age_ok)

    ho = meta["holdout"]

    # -- markdown report ------------------------------------------------------
    c1 = metrics["checklist"]["1_synthetic_recovery"]
    c2 = metrics["checklist"]["2_mock_R_vs_Rhat"]
    c3 = metrics["checklist"]["3_g1_and_age_buffer"]
    c6 = metrics["checklist"]["6_matrix_vs_differential"]
    shape_corr = c2["planted_vs_G0hat_shape_corr"]
    md = f"""# TIM1 Test Report — mock 1347.HK

Generated {metrics['generated']} · N={meta['N_events']} events · L={meta['L']} · units={meta['units']} · primary solver: **{meta['G0_solver']}**{' ⚠ no path had G0(1)>0 — matrix kept with warning' if meta['G0_solver_warning'] else ''}

## 1. Synthetic TIM1 recovery of known G0

Ground truth G0(ℓ)=g1·ℓ^-γ+g∞, AR signs, exact TIM1 generative mid; matrix inversion on N={syn['N']}, L={syn['L']}.

| check | value | bar | result |
| --- | --- | --- | --- |
| Ĝ0(1) > 0 | {c1['g0hat_1']:.4f} | > 0 | {_ok(c1['g0hat_1_positive'])} |
| corr(true G0, Ĝ0) | {c1['corr_true_G0_vs_G0hat']:.3f} | > 0.7 | {_ok(c1['corr_true_G0_vs_G0hat'] > 0.7)} |
| RMSE(true G0, Ĝ0) | {c1['G0_recovery_rmse']:.6g} | report | — |
| shape corr (normalized) | {c1['shape_corr_normalized']:.3f} | report | — |
| corr(R, AĜ0) | {c1['corr_R_vs_Rhat_synth']:.3f} | > 0.9 | {_ok(c1['corr_R_vs_Rhat_synth'] > 0.9)} |

## 2. Full-sample reconstruct (demoted — exact L×L solve ⇒ R²≈1 is tautological)

Not ML-trained — OLS-style deconvolution. Empirical R on tape; score R̃ = A Ĝ0, e = R − R̃.

| metric | formula | full-sample |
| --- | --- | --- |
| SSE | eᵀe | {ols_full['sse']:.6g} |
| R² | 1 − SSE / (R−R̄)ᵀ(R−R̄) | {ols_full['r2']:.6f} |
| RMSE | √(SSE/L) | {ols_full['rmse']:.6g} |
| corr | corr(R, R̃) | {ols_full['R_vs_Rhat_corr']:.6f} |

Plot: `artifacts/R_vs_Rhat.png`. In-sample corr≈1 is expected from the exact L×L solve; holdout (§4) is the honest test.
Planted kernel vs Ĝ0 shape corr (normalized, first {Lp} lags) = {f'{shape_corr:.3f}' if shape_corr is not None else 'n/a'} (informational).

## 3. g(1)=1 and age-buffer S

g(1) = {c3['g_1']:.12f} → exact by construction: {_ok(g1_exact)}.
Age-buffer: take at q={q_take:.0f} (I0={impact:.3f} bps); S(age=1)={c3['S_age1']:.6f} vs I0·g(1)={c3['expected_S_age1']:.6f}; S(age=2)={c3['S_age2']:.6f} vs I0·g(2)={c3['expected_S_age2']:.6f}; S after expiry = {c3['S_after_expiry']:.1f}. Overall: {_ok(c3['pass'])}.

## 4. Train/holdout (headline) — A_test Ĝ₀ vs R_test

Both **matrix** and **differential** scored on the same split; primary = argmax holdout R².

| solver | holdout R² | holdout RMSE | holdout corr | G0_train(1) | ‖Ĝ₀^tr−Ĝ₀^te‖₂ |
| --- | --- | --- | --- | --- | --- |
| matrix | {ho['matrix']['holdout']['r2']:.6f} | {ho['matrix']['holdout']['rmse']:.6g} | {ho['matrix']['holdout']['R_vs_Rhat_corr']:.6f} | {ho['matrix']['G0_train_1']:.4f} | {ho['matrix']['G0_l2_diff']:.4g} |
| differential | {ho['differential']['holdout']['r2']:.6f} | {ho['differential']['holdout']['rmse']:.6g} | {ho['differential']['holdout']['R_vs_Rhat_corr']:.6f} | {ho['differential']['G0_train_1']:.4f} | {ho['differential']['G0_l2_diff']:.4g} |

**Primary = {ho['primary_by_holdout_r2']}** (N_train={ho['n_train']}, N_hold={ho['n_holdout']}).

Winner extras: max|e|={ho['holdout']['max_abs_e']:.6g}; RMSE/std(R)={ho['holdout']['rmse_over_std_R']:.6g}; residual plot `artifacts/holdout_residuals.png`.

## 5. Caveats (explicit)

- **One-day mock → I0 b is not trusted.** i0 stat used: `{i0['stat_used']}` (a={i0['a']:.4f}, b={i0['b']:.4f}); {i0['caveat']}
- All estimates are from a single synthetic session; treat levels as noisy, shapes as indicative only.

## 6. Matrix vs differential G0

| path | G0(1) | note |
| --- | --- | --- |
| matrix (A⁻¹R) | {c6['G0_matrix_1']:.4f} | Taranto permanent-tail assumption |
| differential (Σ=Γ*C) | {c6['G0_differential_1']:.4f} | finite-support deconvolution |

corr(G0_matrix, G0_diff) = {c6['corr_matrix_vs_differential']:.3f}; primary = **{c6['primary']}**
(selected by **holdout R²**, not G0(1)>0 alone — gap matrix {meta.get('G0_matrix_1', float('nan')):.2f} vs diff {meta.get('G0_differential_1', float('nan')):.2f} needs that). Both saved: `G0_matrix.csv`, `G0_differential.csv`.
"""
    (art / "TEST_REPORT.md").write_text(md)
    (art / "test_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics
