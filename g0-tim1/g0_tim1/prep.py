"""Session clean, Lee–Ready, sweep merge, calendar markouts."""

from __future__ import annotations

import numpy as np
import pandas as pd


def session_clean_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    q = quotes.copy()
    q = q.sort_values("exchtime").reset_index(drop=True)
    q = q.dropna(subset=["bid", "ask", "bsize", "asize"])
    q = q[q["bid"] < q["ask"]].copy()
    # drop first/last ~10 min of continuous session already handled in mock;
    # still drop crossed remnants
    return q.reset_index(drop=True)


def session_clean_trades(trades: pd.DataFrame) -> pd.DataFrame:
    t = trades.copy()
    t = t.sort_values("exchtime").reset_index(drop=True)
    t = t.dropna(subset=["price", "size"])
    t = t[t["size"] > 0].copy()
    return t.reset_index(drop=True)


def build_events(trades: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Lee–Ready vs last quote strictly before trade; sweep-merge same-ms same-side."""
    q = session_clean_quotes(quotes)
    tr = session_clean_trades(trades)

    q_ns = q["exchtime"].astype("int64").to_numpy()
    tr_ns = tr["exchtime"].astype("int64").to_numpy()
    idx = np.searchsorted(q_ns, tr_ns, side="left") - 1
    valid = idx >= 0
    # strict before
    strict = np.zeros(len(tr), dtype=bool)
    strict[valid] = q_ns[idx[valid]] < tr_ns[valid]
    keep = valid & strict
    tr = tr.loc[keep].reset_index(drop=True)
    idx = idx[keep]

    bid = q["bid"].to_numpy()[idx]
    ask = q["ask"].to_numpy()[idx]
    mid = 0.5 * (bid + ask)
    price = tr["price"].to_numpy()

    eps = np.zeros(len(tr), dtype=int)
    buy = price >= ask
    sell = price <= bid
    eps[buy] = 1
    eps[sell] = -1
    inside = ~(buy | sell)
    # v1: drop inside-spread prints
    keep2 = ~inside
    tr = tr.loc[keep2].reset_index(drop=True)
    eps = eps[keep2]
    mid = mid[keep2]
    bid = bid[keep2]
    ask = ask[keep2]

    # Sweep merge: same sign, same millisecond
    ms = (tr["exchtime"].astype("int64") // 1_000_000).to_numpy()
    events = []
    i = 0
    n = len(tr)
    while i < n:
        j = i + 1
        while j < n and ms[j] == ms[i] and eps[j] == eps[i]:
            j += 1
        events.append(
            {
                "n": len(events),
                "t": tr["exchtime"].iloc[i],
                "eps": int(eps[i]),
                "q": int(tr["size"].iloc[i:j].sum()),
                "mid_before": float(mid[i]),
                "bid": float(bid[i]),
                "ask": float(ask[i]),
            }
        )
        i = j

    ev = pd.DataFrame(events)
    return ev


def asof_mid(quotes: pd.DataFrame, times: np.ndarray) -> np.ndarray:
    """Last mid with quote time <= u (piecewise constant)."""
    q = session_clean_quotes(quotes)
    q_ns = q["exchtime"].astype("int64").to_numpy()
    mid = (0.5 * (q["bid"] + q["ask"])).to_numpy()
    t_ns = pd.to_datetime(times).astype("int64").to_numpy()
    idx = np.searchsorted(q_ns, t_ns, side="right") - 1
    out = np.full(len(times), np.nan)
    ok = idx >= 0
    out[ok] = mid[idx[ok]]
    return out


def add_markouts(events: pd.DataFrame, quotes: pd.DataFrame, horizons_s=(0.1, 1.0)) -> pd.DataFrame:
    ev = events.copy()
    t0 = ev["t"]
    for h in horizons_s:
        mid_h = asof_mid(quotes, t0 + pd.to_timedelta(h, unit="s"))
        y = ev["eps"] * (mid_h - ev["mid_before"]) / ev["mid_before"] * 1e4
        ev[f"y_{h}s"] = y
    return ev
