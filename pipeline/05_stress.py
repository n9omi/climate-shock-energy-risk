"""
05_stress.py | Step 5: climate stress tests. What would each past storm do to today's book?

Historical-scenario method: for every event, take the actual cumulative price change of each commodity from
2 trading days before to 10 after day 0, and apply it to today's positions (constant notional, no rebalancing):
    P&L_scenario = sum_i  notional_i * ( exp( sum_{tau=-2..+10} r_{i,tau} / 100 ) - 1 )
Compared with today's 10-day 99% VaR (sqrt(10) x the 1-day filtered-HS VaR, the Basel convention) and with the
worst 13-day stretch of the whole sample (whatever caused it), so a climate loss can be put in context.
Outputs: tables/05_*.csv, figures/05_*.png, data/processed/stress.pkl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402
from climrisk import overlay as ov  # noqa: E402
from climrisk.colors import HAZARD_COLOR, MODEL_COLOR, SERIES_COLOR  # noqa: E402,F401
from climrisk.rr import style  # noqa: E402

style.apply()
P = pd.read_pickle(C.DATA_PROC / "prices.pkl")
E = pd.read_pickle(C.DATA_PROC / "events.pkl").sort_values("day0").reset_index(drop=True)
R = P["rets"][list(C.DAILY)]
simple = np.expm1(R / 100)
n = len(R)
H = C.STRESS_WIN[1] - C.STRESS_WIN[0] + 1
print(f"Step 5 | climate stress tests ({H}-day historical scenarios)")

cum = np.expm1(R.rolling(H).sum() / 100)                     # cumulative simple return over the H days ending t
rows = []
for e in E.itertuples():
    end = e.pos + C.STRESS_WIN[1]
    if end >= n or e.pos + C.STRESS_WIN[0] < 1:
        continue
    move = cum.iloc[end]
    row = dict(event=e.short, hazard=e.hazard, day0=e.day0.date(), **{f"{k}_pct": 100 * move[k] for k in C.DAILY})
    for pname, pos in C.POSITIONS.items():
        row[pname] = float(sum(v * move[k] for k, v in pos.items()))
    rows.append(row)
S = pd.DataFrame(rows)

# today's 10-day VaR per position, and the worst H-day stretch in the sample
ctx = []
for pname, pos in C.POSITIONS.items():
    x = sum(simple[k] * v for k, v in pos.items()).values
    v1 = ov.var_fhs(np.r_[x, 0.0], len(x), C.HS_WINDOW, C.VAR_P, C.EWMA_LAMBDA)[0]   # forecast for the next day
    hist = pd.Series(sum(v * cum[k] for k, v in pos.items()).values, index=R.index).dropna()
    worst_i = hist.idxmin()
    sub = S[pname]
    ctx.append(dict(position=pname, var10=float(v1 * np.sqrt(10)), worst_climate=float(sub.min()),
                    worst_climate_event=S.loc[sub.idxmin(), "event"], worst_any=float(hist.min()),
                    worst_any_end=worst_i.date(), climate_scenarios_beyond_var=int((sub < -v1 * np.sqrt(10)).sum()),
                    scenarios=len(sub)))
CTX = pd.DataFrame(ctx)
for pname in C.POSITIONS:
    S[f"{pname} / VaR10"] = S[pname] / CTX.set_index("position").loc[pname, "var10"]
S.to_csv(C.TAB / "05_stress_scenarios.csv", index=False)
CTX.to_csv(C.TAB / "05_stress_context.csv", index=False)
print(CTX.round(0).to_string(index=False))
print(S.sort_values("Book")[["event", "WTI_pct", "Brent_pct", "HenryHub_pct", "Book"]].head(8).round(1).to_string(index=False))

# --- figure: the book under every past storm ------------------------------------------------------------------
b = S.sort_values("Book")
v10 = CTX.set_index("position").loc["Book", "var10"]
fig, ax = plt.subplots(figsize=(9, 0.26 * len(b) + 1.3))
cols = [HAZARD_COLOR[h] for h in b.hazard]
ax.barh(range(len(b)), b.Book / 1e3, color=cols, height=0.62)
ax.axvline(-v10 / 1e3, color=style.STATUS["critical"], lw=1.1, ls="--")
ax.text(-v10 / 1e3, len(b) - 0.2, f" today's 10-day 99% VaR: -${v10 / 1e3:,.0f}k", color=style.STATUS["critical"],
        fontsize=8, va="top")
ax.axvline(0, color=style.INK["axis"], lw=0.8)
ax.set_yticks(range(len(b)), b.event, fontsize=7.8)
ax.invert_yaxis()
ax.set_xlabel("Book P&L if the storm's 13-day price moves happened today ($ thousands)")
ax.set_title("Climate stress test of the desk book (pink: hurricanes, purple: winter storms)")
ax.grid(axis="y", visible=False)
ax.grid(axis="x")
style.save(fig, C.FIG / "05_stress_book.png")
pd.to_pickle(dict(scenarios=S, context=CTX), C.DATA_PROC / "stress.pkl")
print("  wrote tables and figures")
