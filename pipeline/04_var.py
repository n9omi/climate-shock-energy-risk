"""
04_var.py | Step 4: do standard VaR models break down during storms, and does a climate overlay fix it?

For each position (the desk book, a long WTI and a long Henry Hub position), three 99% one-day VaR models
(historical simulation, filtered HS with EWMA, GARCH-t) forecast every day from BACKTEST_START with data up to
the day before. Days from 2 trading days before to 10 after each event form its "risk window".
    Are breaches more frequent inside risk windows?   Fisher's exact test, inside vs outside
    Is VaR still right inside them?                   Kupiec proportion-of-failures test on window days only
    The climate overlay (climrisk.overlay)            scale VaR inside the window by k, learned from past storms only
    What it costs                                     average VaR over the whole backtest, with vs without
Outputs: tables/04_*.csv, figures/04_*.png, data/processed/var.pkl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402

import config as C  # noqa: E402
from climrisk import events as evm, overlay as ov  # noqa: E402
from climrisk.colors import HAZARD_COLOR, MODEL_COLOR  # noqa: E402
from climrisk.rr import style, var_es  # noqa: E402

style.apply()
P = pd.read_pickle(C.DATA_PROC / "prices.pkl")
E = pd.read_pickle(C.DATA_PROC / "events.pkl").sort_values("day0").reset_index(drop=True)
R = P["rets"]
simple = np.expm1(R[list(C.DAILY)] / 100)
n = len(R)
START = C.HS_WINDOW                                    # first day with a full look-back
bt0 = int(R.index.searchsorted(pd.Timestamp(C.BACKTEST_START))) - START
dates = R.index[START:]
print(f"Step 4 | VaR backtests and the climate overlay ({dates[bt0].date()} to {dates[-1].date()})")

# risk windows, in path coordinates (day index minus START)
win = {hz: [np.arange(p + C.RISK_WIN[0], p + C.RISK_WIN[1] + 1) - START for p in E[E.hazard == hz].pos]
       for hz in C.HAZARDS}
names = {hz: E[E.hazard == hz].short.tolist() for hz in C.HAZARDS}
in_win = {hz: evm.window_mask(E[E.hazard == hz].pos.values, n, C.RISK_WIN)[START:] for hz in C.HAZARDS}
in_any = in_win["hurricane"] | in_win["winter"]
bt = np.zeros(len(dates), bool)
bt[bt0:] = True

rows, krows, erows, paths = [], [], [], {}
for pname, pos in C.POSITIONS.items():
    x_full = sum(simple[k] * v for k, v in pos.items()).values
    x = x_full[START:]
    models = {"Historical sim": ov.var_hs(x_full, START, C.HS_WINDOW, C.VAR_P),
              "Filtered HS": ov.var_fhs(x_full, START, C.HS_WINDOW, C.VAR_P, C.EWMA_LAMBDA)}
    models["GARCH-t"], _ = ov.var_garch_t(x_full, START, C.VAR_P, C.GARCH_REFIT_DAYS)
    for m, var in models.items():
        exc = x < -var
        ks = {hz: ov.overlay_k(x, var, win[hz], C.K_CAP, C.MIN_PAST_EVENTS) for hz in C.HAZARDS}
        var_o = var.copy()
        for hz in C.HAZARDS:
            var_o = np.maximum(var_o, ov.apply_overlay(var, win[hz], ks[hz]))
        exc_o = x < -var_o
        inside, outside = bt & in_any, bt & ~in_any
        tab = [[int(exc[inside].sum()), int((~exc[inside]).sum())], [int(exc[outside].sum()), int((~exc[outside]).sum())]]
        odds, p_f = fisher_exact(tab, alternative="greater")
        row = dict(position=pname, model=m, days=int(bt.sum()), exceptions=int(exc[bt].sum()),
                   rate=float(exc[bt].mean()), p_kupiec=var_es.kupiec_pof(exc[bt], C.VAR_P)[1],
                   p_cc=var_es.conditional_coverage(exc[bt], C.VAR_P)[1], window_days=int(inside.sum()),
                   window_exceptions=int(exc[inside].sum()), window_rate=float(exc[inside].mean()),
                   outside_rate=float(exc[outside].mean()), p_fisher=float(p_f),
                   p_kupiec_window=var_es.kupiec_pof(exc[inside], C.VAR_P)[1],
                   overlay_window_exceptions=int(exc_o[inside].sum()), overlay_window_rate=float(exc_o[inside].mean()),
                   overlay_p_kupiec_window=var_es.kupiec_pof(exc_o[inside], C.VAR_P)[1],
                   overlay_rate=float(exc_o[bt].mean()),
                   capital_cost=float(var_o[bt].mean() / var[bt].mean() - 1))
        for hz in C.HAZARDS:
            hz_in = bt & in_win[hz]
            row[f"{hz}_window_days"] = int(hz_in.sum())
            row[f"{hz}_exceptions"] = int(exc[hz_in].sum())
            row[f"{hz}_overlay_exceptions"] = int(exc_o[hz_in].sum())
            row[f"{hz}_mean_k"] = float(np.mean([k for k, w in zip(ks[hz], win[hz]) if (w >= bt0).any()]))
            for ename, w, k in zip(names[hz], win[hz], ks[hz]):
                w = w[(w >= 0) & (w < len(x))]
                if len(w) == 0 or w.max() < bt0:
                    continue
                krows.append(dict(position=pname, model=m, hazard=hz, event=ename, k=float(k)))
                erows.append(dict(position=pname, model=m, hazard=hz, event=ename, day0=str(dates[min(w.min() + 2, len(dates) - 1)].date()),
                                  exceptions=int(exc[w].sum()), overlay_exceptions=int(exc_o[w].sum()),
                                  worst_loss_vs_var=float(np.max(-x[w] / var[w]))))
        rows.append(row)
        paths[(pname, m)] = pd.DataFrame(dict(pnl=x, var=var, var_overlay=var_o, exc=exc, exc_overlay=exc_o,
                                              in_hurricane=in_win["hurricane"], in_winter=in_win["winter"]), index=dates)
    print(f"  {pname}: done")

res = pd.DataFrame(rows)
res.to_csv(C.TAB / "04_var_backtest.csv", index=False)
pd.DataFrame(krows).to_csv(C.TAB / "04_overlay_k.csv", index=False)
pd.DataFrame(erows).to_csv(C.TAB / "04_exceptions_by_event.csv", index=False)
print(res[["position", "model", "rate", "window_days", "window_exceptions", "window_rate", "outside_rate", "p_fisher",
           "overlay_window_exceptions", "capital_cost"]].round(4).to_string(index=False))

# --- figures ---------------------------------------------------------------------------------------------
MC = MODEL_COLOR
fig, ax = plt.subplots(figsize=(9, 3.6))
ylab = []
for i, r_ in enumerate(res.itertuples()):
    ax.plot([r_.outside_rate * 100, r_.window_rate * 100], [i, i], color=style.INK["grid"], lw=2, zorder=1)
    ax.plot(r_.outside_rate * 100, i, "o", ms=7, mfc="white", mec=MC[r_.model], mew=1.6, zorder=2)
    ax.plot(r_.window_rate * 100, i, "o", ms=7, color=MC[r_.model], zorder=3)
    ylab.append(f"{r_.position} · {r_.model}")
ax.axvline(C.VAR_P * 100, color=style.STATUS["critical"], lw=1, ls="--")
ax.text(C.VAR_P * 100, -0.9, " 1% target", color=style.STATUS["critical"], fontsize=8, va="center")
ax.set_yticks(range(len(res)), ylab, fontsize=8)
ax.set_ylim(len(res) - 0.4, -1.4)
ax.set_xlabel("Share of days with a loss beyond 99% VaR (%): hollow = normal days, filled = storm risk windows")
ax.set_title("VaR breaches: inside storm windows vs everywhere else")
ax.grid(axis="y", visible=False)
ax.grid(axis="x")
style.save(fig, C.FIG / "04_breach_rates.png")

fig, ax = plt.subplots(figsize=(9, 3.3))
for i, r_ in enumerate(res.itertuples()):
    ax.annotate("", xy=(r_.overlay_window_rate * 100, i), xytext=(r_.window_rate * 100, i),
                arrowprops=dict(arrowstyle="->", color=MC[r_.model], lw=1.4))
    ax.plot(r_.window_rate * 100, i, "o", ms=6, color=MC[r_.model])
    ax.text(max(r_.window_rate, r_.overlay_window_rate) * 100 + 0.15, i, f"+{r_.capital_cost * 100:.1f}% average VaR",
            va="center", fontsize=7.5, color=style.INK["secondary"])
ax.axvline(C.VAR_P * 100, color=style.STATUS["critical"], lw=1, ls="--")
ax.set_yticks(range(len(res)), ylab, fontsize=8)
ax.invert_yaxis()
ax.set_xlabel("Breach rate inside storm windows (%): dot = model, arrow tip = with the climate overlay")
ax.set_title("The climate overlay: fewer storm-window breaches, and what it costs")
ax.grid(axis="y", visible=False)
ax.grid(axis="x")
style.save(fig, C.FIG / "04_overlay.png")

d = paths[("Long Henry Hub $1mm", "Filtered HS")].loc["2017":]
fig, ax = plt.subplots(figsize=(9, 3.6))
for col, c in (("in_hurricane", HAZARD_COLOR["hurricane"]), ("in_winter", HAZARD_COLOR["winter"])):
    m = d[col].values.astype(int)
    edges = np.flatnonzero(np.diff(np.r_[0, m, 0]))
    for a, b in zip(edges[::2], edges[1::2]):
        ax.axvspan(d.index[a], d.index[min(b, len(d) - 1)], color=c, alpha=0.15, lw=0)
ax.plot(d.index, d.pnl / 1e3, color=style.INK["muted"], lw=0.5, label="Daily P&L")
ax.plot(d.index, -d["var"] / 1e3, color=MODEL_COLOR["Filtered HS"], lw=1.0, label="-VaR (filtered HS)")
ax.plot(d.index, -d.var_overlay / 1e3, color=style.INK["primary"], lw=0.8, ls="--", label="-VaR with climate overlay")
ax.plot(d.index[d.exc], d.pnl[d.exc] / 1e3, "v", ms=4, color=style.STATUS["critical"], label="Breach")
ax.set_ylabel("$ thousands")
ax.set_ylim(max(d.pnl.min(), -d.var_overlay.max()) / 1e3 * 1.15, d.pnl.max() / 1e3 * 1.1)
ax.set_title("Long $1mm Henry Hub: P&L, VaR and breaches (shaded: hurricane and winter-storm risk windows)")
ax.legend(ncol=4, loc="lower left", fontsize=7.5)
style.save(fig, C.FIG / "04_henryhub_var.png")
pd.to_pickle(dict(results=res, paths=paths, k=pd.DataFrame(krows), by_event=pd.DataFrame(erows)), C.DATA_PROC / "var.pkl")
print("  wrote tables and figures")
