"""Synthetic TIM1 ground truth: known G0 → events → recovery. Shared by tests + report."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .tim1 import estimate_c_r, invert_tim1
from .holdout import evaluate_reconstruct


def planted_kernel(L: int, g1: float = 0.002, gamma: float = 0.4, g_inf: float = 0.0005) -> np.ndarray:
    """Power-law-ish bare kernel G0(ℓ)=g1 ℓ^-γ + g∞ for ℓ=1..L (permanent tail)."""
    ell = np.arange(1, L + 1, dtype=float)
    return g1 * ell ** -gamma + g_inf


def ar_signs(N: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    """ε with E[ε_n ε_{n+1}]=phi: keep previous sign w.p. (1+phi)/2."""
    eps = np.ones(N, dtype=float)
    keep = rng.random(N) < (1.0 + phi) / 2.0
    for i in range(1, N):
        eps[i] = eps[i - 1] if keep[i] else -eps[i - 1]
    return eps


def make_events(
    N: int = 4000,
    L_true: int = 40,
    phi: float = 0.35,
    g1: float = 0.002,
    gamma: float = 0.4,
    g_inf: float = 0.0005,
    noise: float = 0.0,
    seed: int = 0,
) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Exact TIM1 generative: m_n = m0 + Σ_{j<n} G0(n-j) ε_j (+ cumulative noise walk).
    Permanent tail keeps the Taranto A-map assumption (impact never fully decays).
    """
    rng = np.random.default_rng(seed)
    true_G0 = planted_kernel(L_true, g1, gamma, g_inf)
    eps = ar_signs(N, phi, rng)

    # full-history impact level: lvl[n] = Σ_{k=1..n} G0(k) ε_{n-k}  (kernel index k-1)
    kernel_full = np.concatenate([[0.0], planted_kernel(N, g1, gamma, g_inf)])
    lvl = np.convolve(eps, kernel_full, mode="full")[:N]

    mid = 100.0 + lvl
    if noise > 0:
        mid = mid + np.cumsum(rng.normal(0.0, noise, size=N))

    ev = pd.DataFrame(
        {
            "n": np.arange(N),
            "t": pd.date_range("2026-01-01", periods=N, freq="s"),
            "eps": eps.astype(int),
            "q": np.full(N, 1000),
            "mid_before": mid,
        }
    )
    return ev, true_G0


def synthetic_recovery(**kwargs) -> dict:
    """Run TIM1 matrix inversion on synthetic events; return recovery diagnostics."""
    L_fit = int(kwargs.pop("L_fit", 0)) or None
    ridge = float(kwargs.pop("ridge", 1e-8))
    ev, true_G0 = make_events(**kwargs)
    L = L_fit or len(true_G0)
    C, R = estimate_c_r(ev, L=L, units="price")
    G0_hat, A, R_hat = invert_tim1(C, R, ridge=ridge)
    Lc = min(len(true_G0), L)
    recon = evaluate_reconstruct(R, R_hat)
    g0_rmse = float(np.sqrt(np.mean((true_G0[:Lc] - G0_hat[:Lc]) ** 2)))
    return {
        "corr_true_vs_g0hat": float(np.corrcoef(true_G0[:Lc], G0_hat[:Lc])[0, 1]),
        "G0_recovery_rmse": g0_rmse,
        "corr_R_vs_Rhat": recon["R_vs_Rhat_corr"],
        "r2": recon["r2"],
        "rmse": recon["rmse"],
        "sse": recon["sse"],
        "g0hat_1": float(G0_hat[0]),
        "g0_true_1": float(true_G0[0]),
        "L": L,
        "N": len(ev),
        "true_G0": true_G0,
        "G0_hat": G0_hat,
        "R": R,
        "R_hat": R_hat,
        "C": C,
    }
