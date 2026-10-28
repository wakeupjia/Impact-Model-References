"""C, R estimation and TIM1 bare G0 inversion (Taranto matrix form)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def estimate_c_r(events: pd.DataFrame, L: int, units: str = "price") -> tuple[np.ndarray, np.ndarray]:
    """
    Trade-time C(0..L), R(1..L).
    units: 'price' → raw mid diff; 'bps' → mid diff / mid_before * 1e4
    Returns C length L+1, R length L (lags 1..L).
    """
    eps = events["eps"].to_numpy(dtype=float)
    mid = events["mid_before"].to_numpy(dtype=float)
    N = len(eps)
    if N <= L + 2:
        raise ValueError(f"N={N} too small for L={L}")

    C = np.zeros(L + 1)
    C[0] = 1.0
    R = np.zeros(L)
    for ell in range(1, L + 1):
        e0 = eps[: N - ell]
        e1 = eps[ell:]
        C[ell] = float(np.mean(e0 * e1))
        dm = mid[ell:] - mid[: N - ell]
        if units == "bps":
            dm = dm / mid[: N - ell] * 1e4
        R[ell - 1] = float(np.mean(dm * e0))
    return C, R


def build_A(C: np.ndarray, L: int) -> np.ndarray:
    """
    A[ℓ,j] for 0-based indices corresponding to 1-based ℓ,j=1..L:
    A_ℓj = 1_{j<=ℓ} C(ℓ-j) + 1_{j>ℓ} C(j-ℓ) - C(j)
    C indexed as C[0]=1, C[k]=C(k).
    """
    A = np.zeros((L, L))
    for ell in range(1, L + 1):  # 1-based
        for j in range(1, L + 1):
            if j <= ell:
                term = C[ell - j]
            else:
                term = C[j - ell]
            A[ell - 1, j - 1] = term - C[j]
    return A


def invert_tim1(
    C: np.ndarray,
    R: np.ndarray,
    ridge: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Solve R = A G0. Returns G0 (len L), A, R_hat.
    """
    L = len(R)
    A = build_A(C, L)
    if ridge > 0:
        A_reg = A + ridge * np.eye(L)
    else:
        A_reg = A
    G0 = np.linalg.solve(A_reg, R)
    R_hat = A @ G0
    return G0, A, R_hat


def invert_tim1_differential(events: pd.DataFrame, C: np.ndarray, L: int, units: str = "price"):
    """
    Taranto differential path: Σ = Γ * C, then G0(ℓ)=sum_{i<ℓ} Γ(i).
    Σ(ℓ)=E[r_{n+ℓ} ε_n], r_n = m_{n+1}-m_n.
    """
    eps = events["eps"].to_numpy(dtype=float)
    mid = events["mid_before"].to_numpy(dtype=float)
    r = mid[1:] - mid[:-1]
    if units == "bps":
        r = r / mid[:-1] * 1e4
    # align: r[n] is return after trade n toward n+1; length N-1
    N = len(eps)
    Sigma = np.zeros(L)
    for ell in range(1, L + 1):
        # r_{n+ell} with sign ε_n ; n from 0 .. N-2-ell
        # r index = n+ell (return between n+ell and n+ell+1) — Taranto uses r_{n+ℓ}
        # Use r at index n+ell-1 as move into event n+ell mid? Prefer:
        # r_k = m_{k+1}-m_k for k=0..N-2; Σ(ℓ)=mean r_{n+ℓ} ε_n for n with n+ℓ <= N-2
        max_n = N - 2 - ell
        if max_n < 0:
            Sigma[ell - 1] = 0.0
            continue
        # r_{n+ℓ}: index n+ell
        vals = []
        for n in range(0, max_n + 1):
            vals.append(r[n + ell] * eps[n])
        Sigma[ell - 1] = float(np.mean(vals)) if vals else 0.0

    # Build Toeplitz convolution matrix for Σ = Γ * C truncated
    # Σ(ℓ) = sum_{k=1..ℓ} Γ(k) C(ℓ-k)  (causal) — common discrete form
    M = np.zeros((L, L))
    for ell in range(1, L + 1):
        for k in range(1, ell + 1):
            M[ell - 1, k - 1] = C[ell - k]
    try:
        Gamma = np.linalg.solve(M + 1e-10 * np.eye(L), Sigma)
    except np.linalg.LinAlgError:
        Gamma = np.linalg.lstsq(M, Sigma, rcond=None)[0]

    G0 = np.cumsum(Gamma)  # G0(1)=Γ(1), G0(2)=Γ(1)+Γ(2), ...
    return G0, Gamma, Sigma


def g_from_G0(G0: np.ndarray) -> np.ndarray:
    g = G0 / G0[0]
    return g


def choose_L(N: int, preferred: int = 100) -> int:
    # N >> L; keep L <= N/20 and <= preferred
    L = min(preferred, max(10, N // 20))
    return int(L)


def save_series(path: Path, lags: np.ndarray, values: np.ndarray, name: str) -> None:
    pd.DataFrame({"lag": lags, name: values}).to_csv(path, index=False)
