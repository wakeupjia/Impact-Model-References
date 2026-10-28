"""Generate one-day HK-like trades + BBO quotes for 1347.HK with a planted G0 kernel.

Trades carry persistent signs (AR). Quote mids react to each aggressive print with a
decaying signed response in *trade time*: after n prints the injected level is
m0 + tick * Σ_{j≤n} G0_planted(n+1-j) ε_j, with G0_planted(ℓ) = g1·ℓ^-γ (finite
support L_planted). The pipeline measures everything in event (trade) time, so the
planted kernel is exactly the ground truth the TIM1 inversion should dig out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _session_seconds() -> np.ndarray:
    """Continuous HK session: 09:30–12:00 and 13:00–16:00 (local), as seconds from midnight."""
    morning = np.arange(9 * 3600 + 30 * 60 + 600, 12 * 3600 - 600)  # drop first/last 10m of morning
    afternoon = np.arange(13 * 3600 + 600, 16 * 3600 - 600)
    return np.concatenate([morning, afternoon])


def planted_kernel_ticks(L: int, g1: float, gamma: float) -> np.ndarray:
    return g1 * np.arange(1, L + 1, dtype=float) ** -gamma


def generate_day(
    sym: str = "1347.HK",
    date: str = "2026-10-27",
    seed: int = 42,
    n_quotes: int = 25_000,
    n_trades: int = 4_000,
    start_mid: float = 3.45,
    tick: float = 0.01,
    planted_g1: float = 0.6,
    planted_gamma: float = 0.5,
    planted_L: int = 60,
    sign_keep: float = 0.7,
    mid_noise_ticks: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Returns (trades, quotes, planted_meta). planted_meta documents the kernel that
    was injected so run_meta / the test report can compare Ĝ0 against ground truth.
    """
    rng = np.random.default_rng(seed)
    day = pd.Timestamp(date)
    secs = _session_seconds()
    t0 = day + pd.Timedelta(seconds=int(secs[0]))
    t1 = day + pd.Timedelta(seconds=int(secs[-1]))

    # --- Trades first: times + persistent aggressor signs -------------------
    tr_times = np.sort(rng.uniform(t0.value, t1.value, size=n_trades)).astype("datetime64[ns]")
    eps = np.ones(n_trades, dtype=float)
    keep = rng.random(n_trades) < sign_keep
    for i in range(1, n_trades):
        eps[i] = eps[i - 1] if keep[i] else -eps[i - 1]

    # --- Event-time impact level: lvl[n] = Σ_{k=1..L} G0p(k) ε_{n-k} --------
    kernel = planted_kernel_ticks(planted_L, planted_g1, planted_gamma)
    # lvl[n] = impact level after prints 0..n-1 have landed; keep index n_trades (all prints)
    lvl = np.convolve(eps, np.concatenate([[0.0], kernel]), mode="full")[: n_trades + 1]

    # --- Quotes: mid = injected level of all prints so far + noise ----------
    q_times = np.sort(rng.uniform(t0.value, t1.value, size=n_quotes)).astype("datetime64[ns]")
    tr_ns = tr_times.astype("int64")
    q_ns = q_times.astype("int64")
    n_prior = np.searchsorted(tr_ns, q_ns, side="right")  # prints fully reflected in quote i
    mid = start_mid + tick * lvl[n_prior]
    mid = mid + tick * rng.normal(0.0, mid_noise_ticks, size=n_quotes)
    mid = np.maximum(mid, tick * 50)  # floor

    spread_ticks = rng.choice([1, 1, 1, 2], size=n_quotes)  # mostly 1-tick
    half = spread_ticks * tick / 2.0
    bid = np.round((mid - half) / tick) * tick
    ask = np.round((mid + half) / tick) * tick
    ask = np.maximum(ask, bid + tick)  # ensure ask > bid
    bsize = rng.integers(500, 8000, size=n_quotes) * 100  # board lots-ish
    asize = rng.integers(500, 8000, size=n_quotes) * 100

    quotes = pd.DataFrame(
        {
            "date": day.date(),
            "sym": sym,
            "exchtime": pd.to_datetime(q_times),
            "bid": bid,
            "ask": ask,
            "bsize": bsize,
            "asize": asize,
        }
    )

    # --- Trade prices at the touch of the last quote strictly before -------
    idx = np.searchsorted(q_ns, tr_ns, side="left") - 1
    idx = np.clip(idx, 0, len(quotes) - 1)
    equal = q_ns[idx] >= tr_ns
    idx[equal] = np.maximum(0, idx[equal] - 1)

    qb = bid[idx]
    qa = ask[idx]
    price = np.where(eps > 0, qa, qb)
    flip = rng.random(n_trades) < 0.03  # occasional inside print (dropped downstream)
    price = np.where(flip, (qb + qa) / 2.0, price)

    size = (rng.lognormal(mean=7.5, sigma=0.85, size=n_trades)).astype(int)
    size = np.clip(size, 200, 200_000)
    size = (size // 100) * 100
    size = np.maximum(size, 100)

    trades = pd.DataFrame(
        {
            "date": day.date(),
            "sym": sym,
            "exchtime": pd.to_datetime(tr_times),
            "price": price,
            "size": size,
            "realtrade": 1,
            "tradetype": "",
            "salescond": "",
        }
    )

    planted = {
        "kernel": "g1 * lag^-gamma (ticks), finite support L_planted, in trade time",
        "g1_ticks": planted_g1,
        "gamma": planted_gamma,
        "L_planted": planted_L,
        "sign_keep": sign_keep,
        "mid_noise_ticks": mid_noise_ticks,
        "seed": seed,
    }
    return trades.reset_index(drop=True), quotes.reset_index(drop=True), planted


def save_mock(data_dir: str, **kwargs) -> tuple[str, str, dict]:
    trades, quotes, planted = generate_day(**kwargs)
    tp = f"{data_dir}/trades_1347HK.parquet"
    qp = f"{data_dir}/quotes_1347HK.parquet"
    trades.to_parquet(tp, index=False)
    quotes.to_parquet(qp, index=False)
    trades.to_csv(f"{data_dir}/trades_1347HK.csv", index=False)
    quotes.to_csv(f"{data_dir}/quotes_1347HK.csv", index=False)
    return tp, qp, planted
