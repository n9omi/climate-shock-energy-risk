"""
eventstudy.py | Did prices move more than usual around the events? (MacKinlay, 1997; Brown & Warner, 1985)

Notation, for one series and one event with day 0 at trading position p (returns r_t in %):
    normal return       mu_hat = mean of r over the estimation window [p-250, p-21]
    abnormal return     AR_tau = r_{p+tau} - mu_hat
    cumulative          CAR[a,b] = sum_{tau=a..b} AR_tau
    abnormal volatility AV = log( RMS(r over [0,+10]) / RMS(r over [-30,-11]) )   (0 = no change; log 2 = doubled)
                        The baseline is the month just before, not the whole year: a long window would be
                        inflated by earlier crashes (2020 hurricanes would be compared with the COVID spring).
Across N events:
    t-test      mean(CAR) / (SD(CAR) / sqrt(N))                     (cross-sectional; robust to event-induced variance)
    sign test   share of events with CAR > 0, binomial p against 1/2
    placebo     the same average on month-matched random dates with no event nearby, N_PLACEBO times;
                p = two-sided share of placebo averages at least as extreme as the real one
Hurricane season and winter are volatile anyway, so the placebo draws dates from the same calendar months:
it asks whether the event beats an ordinary day in the same season, not an ordinary day.
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def valid_positions(pos, n: int, est=(-250, -21), rel=(-20, 30)) -> np.ndarray:
    pos = np.asarray(pos, int)
    return (pos + min(est[0], rel[0]) >= 1) & (pos + rel[1] < n)


def abnormal(r: np.ndarray, pos, est=(-250, -21), rel=(-20, 30)):
    """
    AR for every event (rows) and relative day rel[0]..rel[1] (columns), plus the estimation-window SD.
    r: returns for ONE series (length n). Events without a full window must be removed first (valid_positions).
    """
    r = np.asarray(r, float)
    pos = np.asarray(pos, int)
    e_idx = pos[:, None] + np.arange(est[0], est[1] + 1)[None, :]
    est_r = r[e_idx]
    mu = est_r.mean(axis=1)
    sd = est_r.std(axis=1, ddof=1)
    w_idx = pos[:, None] + np.arange(rel[0], rel[1] + 1)[None, :]
    return r[w_idx] - mu[:, None], mu, sd


def car(ar: np.ndarray, rel0: int, window: tuple[int, int]) -> np.ndarray:
    a, b = window[0] - rel0, window[1] - rel0
    return ar[:, a:b + 1].sum(axis=1)


def abnormal_vol(r: np.ndarray, pos, window=(0, 10), base=(-30, -11)) -> np.ndarray:
    """log of the volatility (RMS return) in `window` relative to the `base` window just before."""
    r = np.asarray(r, float)
    pos = np.asarray(pos, int)
    w = r[pos[:, None] + np.arange(window[0], window[1] + 1)[None, :]]
    b = r[pos[:, None] + np.arange(base[0], base[1] + 1)[None, :]]
    return np.log(np.sqrt(np.mean(w ** 2, axis=1)) / np.sqrt(np.mean(b ** 2, axis=1)))


def t_test(x) -> tuple[float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or np.std(x, ddof=1) == 0:
        return float("nan"), float("nan")
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return float(t), float(2 * stats.t.sf(abs(t), len(x) - 1))


def sign_test(x) -> tuple[float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x) & (x != 0)]
    if len(x) == 0:
        return float("nan"), float("nan")
    k = int((x > 0).sum())
    return k / len(x), float(stats.binomtest(k, len(x), 0.5).pvalue)


def placebo_pool(dates, n: int, event_pos, buffer: int, est=(-250, -21), rel=(-20, 30)) -> dict[int, np.ndarray]:
    """Candidate placebo positions for each calendar month: full windows available, far from every real event."""
    ok = valid_positions(np.arange(n), n, est, rel)
    for p in np.asarray(event_pos, int):
        ok[max(p - buffer, 0): p + buffer + 1] = False
    months = np.asarray(dates.month)
    return {m: np.flatnonzero(ok & (months == m)) for m in range(1, 13)}


def placebo_draws(event_months, pool: dict, n_draws: int, seed: int = 0) -> np.ndarray:
    """(n_draws x n_events) placebo positions; event i's stand-in comes from event i's calendar month."""
    rng = np.random.default_rng(seed)
    cols = [rng.choice(pool[m], size=n_draws, replace=True) for m in event_months]
    return np.column_stack(cols)


def placebo_p(observed: float, placebo_means: np.ndarray) -> float:
    """Two-sided placebo p-value: how often a same-season random set is at least as extreme."""
    pm = np.asarray(placebo_means, float)
    lo = (1 + np.sum(pm <= observed)) / (1 + len(pm))
    hi = (1 + np.sum(pm >= observed)) / (1 + len(pm))
    return float(min(1.0, 2 * min(lo, hi)))


def bh_qvalues(p) -> np.ndarray:
    """Benjamini-Hochberg false-discovery-rate q-values (NaNs kept as NaN)."""
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    pv = p[ok]
    m = len(pv)
    if m == 0:
        return q
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q
