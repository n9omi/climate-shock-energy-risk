"""
overlay.py | One-day 99% VaR three standard ways, and a climate overlay that scales it up during storms.

P&L x_t in dollars (losses negative); VaR_t is a positive loss forecast made with data up to t-1.
    Historical simulation   VaR_t = -q_p( x_{t-500..t-1} )
    Filtered HS (EWMA)      VaR_t = -q_p( x_s / sigma_s  for s in t-500..t-1 ) * sigma_t,   sigma^2 from EWMA(0.94)
    GARCH(1,1)-t            VaR_t from a Student-t with the GARCH variance forecast; re-estimated every 250 days
The estimators (EWMA, GARCH-t MLE, Student-t quantile) come from regime_risk.

Climate overlay, for each hazard separately. During event j's risk window (day -2 to +10):
    VaR*_t = k_j * VaR_t,   k_j = clip( sqrt( sum x^2 / sum (VaR/z)^2 ), 1, K_CAP )
where both sums run over the risk windows of EARLIER events of the same hazard, using only days before
event j's window opens, and z = 2.326 turns a 99% VaR into the standard deviation it implies. In words:
"in past storms, P&L moved k times more than the model expected, so scale it by k this time."
With fewer than MIN_PAST_EVENTS earlier events, k = 1.
"""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.stats import norm

from .rr import var_es, volatility

Z99 = float(norm.ppf(0.99))


def var_hs(x: np.ndarray, start: int, window: int = 500, p: float = 0.01) -> np.ndarray:
    win = sliding_window_view(np.asarray(x, float), window)[start - window: len(x) - window]
    k = max(int(np.floor(window * p)), 1)
    return -np.sort(win, axis=1)[:, k - 1]


def var_fhs(x: np.ndarray, start: int, window: int = 500, p: float = 0.01, lam: float = 0.94) -> np.ndarray:
    x = np.asarray(x, float)
    sig = np.sqrt(volatility.ewma(x, lam))                  # sig_t: forecast for day t from data to t-1
    z = x / sig
    zw = sliding_window_view(z, window)[start - window: len(x) - window]
    k = max(int(np.floor(window * p)), 1)
    return -np.sort(zw, axis=1)[:, k - 1] * sig[start:]


def var_garch_t(x: np.ndarray, start: int, p: float = 0.01, refit: int = 250) -> tuple[np.ndarray, list[dict]]:
    """Expanding-window GARCH(1,1)-t, re-estimated every `refit` days. Returns (VaR path, fitted parameters)."""
    x = np.asarray(x, float)
    out = np.empty(len(x) - start)
    fits = []
    for b0 in range(start, len(x), refit):
        b1 = min(b0 + refit, len(x))
        s = x[:b0].std()
        y = x[:b1] / s                                      # scale to ~unit variance for a stable fit
        f = volatility.garch_fit(y[:b0])
        h, _ = volatility.garch_filter(y, f["mu"], f["omega"], f["alpha"], f["beta"])
        v, _ = var_es.t_var_es(f["mu"], np.sqrt(h[b0:b1]), f["nu"], p)
        out[b0 - start: b1 - start] = v * s
        fits.append(dict(refit_at=b0, persistence=f["persistence"], nu=f["nu"]))
    return out, fits


def overlay_k(x: np.ndarray, var: np.ndarray, windows: list[np.ndarray], k_cap: float = 3.0,
              min_past: int = 2) -> np.ndarray:
    """
    k for each event (in date order) from earlier events only. `windows[j]` holds the positions (in x/var)
    of event j's risk window. Days on or after the first day of window j are never used for k_j.
    """
    x, var = np.asarray(x, float), np.asarray(var, float)
    n = len(x)
    windows = [np.asarray(w, int)[(np.asarray(w, int) >= 0) & (np.asarray(w, int) < n)] for w in windows]
    ks = np.ones(len(windows))
    for j, wj in enumerate(windows):
        if j < min_past or len(wj) == 0:
            continue
        cutoff = wj.min()
        past = np.concatenate([w[w < cutoff] for w in windows[:j]]) if j else np.array([], int)
        past = past[np.isfinite(var[past])] if len(past) else past
        if len(past) < 5:
            continue
        ratio = np.sqrt(np.sum(x[past] ** 2) / np.sum((var[past] / Z99) ** 2))
        ks[j] = float(np.clip(ratio, 1.0, k_cap))
    return ks


def apply_overlay(var: np.ndarray, windows: list[np.ndarray], ks: np.ndarray) -> np.ndarray:
    out = np.asarray(var, float).copy()
    scale = np.ones(len(out))
    for w, k in zip(windows, ks):
        w = w[(w >= 0) & (w < len(out))]
        scale[w] = np.maximum(scale[w], k)
    return out * scale
