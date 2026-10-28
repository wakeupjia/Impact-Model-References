"""Fit I0(q) = a q^b from short-horizon markouts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def fit_i0(events: pd.DataFrame, y_col: str = "y_1.0s", n_buckets: int = 5) -> dict:
    df = events[["q", y_col]].dropna().copy()
    df = df[np.isfinite(df[y_col]) & (df["q"] > 0)]
    if len(df) < n_buckets:
        raise ValueError(f"Need >= {n_buckets} events for I0 fit, got {len(df)}")

    df = df.sort_values("q")
    # quintiles by rank
    df["bucket"] = pd.qcut(df["q"], q=n_buckets, duplicates="drop")
    rows = []
    for b, g in df.groupby("bucket", observed=True):
        q_med = float(g["q"].median())
        y_med = float(g[y_col].median())
        y_mean = float(g[y_col].mean())
        rows.append(
            {
                "bucket": str(b),
                "n": int(len(g)),
                "q_median": q_med,
                "y_median_bps": y_med,
                "y_mean_bps": y_mean,
            }
        )
    buckets = pd.DataFrame(rows)
    # bucket medians ~0 (typical one-day mock) carry no log-fit signal: fall back to means
    n_pos_med = int((buckets["y_median_bps"] > 0).sum())
    n_pos_mean = int((buckets["y_mean_bps"] > 0).sum())
    if n_pos_med >= 2:
        stat_used = "median"
    elif n_pos_mean >= 2:
        stat_used = "mean"
    else:
        stat_used = "fallback"
    col = {"median": "y_median_bps", "mean": "y_mean_bps"}.get(stat_used)

    if col is None:
        # fallback: weak constant impact
        a, b = float(max(df[y_col].median(), 1e-6)), 0.5
    else:
        # log-fit only on positive bucket stats of the chosen column
        fit_df = buckets[buckets[col] > 0]
        x = np.log(fit_df["q_median"].to_numpy())
        y = np.log(fit_df[col].to_numpy())
        b_coef, log_a = np.polyfit(x, y, 1)
        a, b = float(np.exp(log_a)), float(b_coef)

    return {
        "a": a,
        "b": b,
        "n": int(len(df)),
        "y_col": y_col,
        "stat_used": stat_used,
        "n_positive_buckets": {"median": n_pos_med, "mean": n_pos_mean},
        "buckets": buckets.to_dict(orient="records"),
        "formula": "I0(q) = a * q**b  (bps of mid)",
        "units": "bps",
        "caveat": "One-day mock: I0 b is not trusted (noisy, sign-diluted); do not ship.",
    }


def i0_bps(q: float | np.ndarray, fit: dict) -> float | np.ndarray:
    return fit["a"] * np.asarray(q, dtype=float) ** fit["b"]


def save_i0(fit: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(fit, indent=2))
