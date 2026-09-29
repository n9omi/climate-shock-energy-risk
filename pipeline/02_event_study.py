"""
02_event_study.py | Step 2: did oil and gas prices move more than usual around hurricanes and winter storms?

For each hazard and series: cumulative abnormal returns (direction) and abnormal volatility (size), each tested
three ways: a cross-sectional t-test, a sign test, and a month-matched placebo (N_PLACEBO random sets of dates
from the same calendar months with no event nearby). Benjamini-Hochberg q-values control false discoveries
across every test in the table.
Outputs: tables/02_*.csv, figures/02_*.png, data/processed/eventstudy.pkl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402
from climrisk import eventstudy as es  # noqa: E402
from climrisk.colors import HAZARD_COLOR, MODEL_COLOR, SERIES_COLOR  # noqa: E402,F401
from climrisk.rr import style  # noqa: E402

style.apply()
P = pd.read_pickle(C.DATA_PROC / "prices.pkl")
E = pd.read_pickle(C.DATA_PROC / "events.pkl")
R = P["rets"][C.SERIES]
n = len(R)
REL0, REL1 = C.PATH_WIN
rel = np.arange(REL0, REL1 + 1)
print("Step 2 | event study")

valid = es.valid_positions(E.pos.values, n, C.EST_WIN, C.PATH_WIN)
E = E[valid].reset_index(drop=True)
pool = es.placebo_pool(R.index, n, E.pos.values, C.PLACEBO_BUFFER, C.EST_WIN, C.PATH_WIN)
allpos = np.flatnonzero(es.valid_positions(np.arange(n), n, C.EST_WIN, C.PATH_WIN))

rows, per_event, paths = [], [], []
draws = {}
for hz, label in C.HAZARDS.items():
    ev = E[E.hazard == hz]
    draws[hz] = es.placebo_draws(ev.month.values, pool, C.N_PLACEBO, seed=C.SEED + len(ev))
    print(f"  {label}: {len(ev)} events with a full window")
    for s in C.SERIES:
        r = R[s].values
        ar, mu, sd = es.abnormal(r, ev.pos.values, C.EST_WIN, C.PATH_WIN)
        # the same statistics on every possible day, so placebo sets are just look-ups
        ar_all = np.full((n, len(rel)), np.nan)
        sd_all = np.full(n, np.nan)
        ar_all[allpos], _, sd_all[allpos] = es.abnormal(r, allpos, C.EST_WIN, C.PATH_WIN)
        measures = {w: (es.car(ar, REL0, win), es.car(ar_all, REL0, win)) for w, win in C.WINDOWS.items()}
        av_all = np.full(n, np.nan)
        av_all[allpos] = es.abnormal_vol(r, allpos, C.VOL_WIN, C.VOL_BASE)
        measures["Abnormal volatility [0,+10]"] = (es.abnormal_vol(r, ev.pos.values, C.VOL_WIN, C.VOL_BASE), av_all)
        for m, (x, x_all) in measures.items():
            t, pt = es.t_test(x)
            share, ps = es.sign_test(x)
            plac = x_all[draws[hz]].mean(axis=1)
            rows.append(dict(hazard=hz, series=s, measure=m, n=len(x), mean=float(np.mean(x)),
                             median=float(np.median(x)), t_stat=t, p_ttest=pt, share_positive=share, p_sign=ps,
                             placebo_mean=float(np.mean(plac)), placebo_p05=float(np.quantile(plac, 0.05)),
                             placebo_p95=float(np.quantile(plac, 0.95)), p_placebo=es.placebo_p(float(np.mean(x)), plac)))
        cum = np.cumsum(ar, axis=1)
        pl_paths = np.cumsum(ar_all[draws[hz]], axis=2).mean(axis=1)          # draws x days
        paths.append(pd.DataFrame(dict(hazard=hz, series=s, day=rel, mean_car=cum.mean(axis=0),
                                       placebo_lo=np.quantile(pl_paths, 0.05, axis=0),
                                       placebo_hi=np.quantile(pl_paths, 0.95, axis=0))))
        full = es.car(ar, REL0, C.WINDOWS[C.MAIN_WINDOW])
        av = es.abnormal_vol(r, ev.pos.values, C.VOL_WIN, C.VOL_BASE)
        worst = ar[:, (0 - REL0):(10 - REL0 + 1)]
        for i, e in enumerate(ev.itertuples()):
            per_event.append(dict(event=e.short, hazard=hz, day0=e.day0.date(), series=s, car_full=full[i],
                                  abnormal_vol=av[i], vol_multiple=float(np.exp(av[i])),
                                  biggest_day=float(worst[i, np.argmax(np.abs(worst[i]))])))

res = pd.DataFrame(rows)
# primary tests (fixed in config before the run): the full-window CAR and abnormal volatility, 2 hazards x 4 series.
# The placebo is the primary test (it handles seasonality and skew); FDR is controlled across those 16 tests.
res["primary"] = res.measure.isin([C.MAIN_WINDOW, "Abnormal volatility [0,+10]"])
res["q_bh"] = np.nan
res.loc[res.primary, "q_bh"] = es.bh_qvalues(res.loc[res.primary, "p_placebo"].values)
res.to_csv(C.TAB / "02_event_study.csv", index=False)
pe = pd.DataFrame(per_event)
pe.to_csv(C.TAB / "02_event_cars.csv", index=False)
paths = pd.concat(paths, ignore_index=True)
paths.to_csv(C.TAB / "02_average_paths.csv", index=False)
show = res[res.measure.isin([C.MAIN_WINDOW, "Abnormal volatility [0,+10]"])]
print(show[["hazard", "series", "measure", "n", "mean", "p_ttest", "p_placebo", "q_bh"]].round(3).to_string(index=False))

# --- figures --------------------------------------------------------------------------------------
COL = SERIES_COLOR
for hz, label in C.HAZARDS.items():
    fig, axes = plt.subplots(1, 4, figsize=(9, 2.9), sharex=True)
    for ax, s in zip(axes, C.SERIES):
        p = paths[(paths.hazard == hz) & (paths.series == s)]
        ax.fill_between(p.day, p.placebo_lo, p.placebo_hi, color=style.INK["grid"], alpha=0.9, lw=0,
                        label="Same-season placebo, 90%")
        ax.plot(p.day, p.mean_car, color=COL[s], lw=1.6, label="Events, average")
        ax.axvline(0, color=style.INK["secondary"], lw=0.8, ls="--")
        ax.axhline(0, color=style.INK["axis"], lw=0.6)
        ax.set_title(C.LABELS[s], fontsize=9)
        ax.set_xlabel("Trading days from day 0", fontsize=8)
    axes[0].set_ylabel("Cumulative abnormal return (%)")
    axes[0].legend(loc="upper left", fontsize=7)
    n_ev = int(res[(res.hazard == hz)].n.iloc[0])
    fig.suptitle(f"{C.HAZ_PLURAL[hz]} ({n_ev} events): average cumulative abnormal return", x=0.01, ha="left",
                 fontweight="bold", fontsize=10.5)
    fig.tight_layout()
    style.save(fig, C.FIG / f"02_car_paths_{hz}.png")

# abnormal volatility: dots with the placebo band (the axis is a multiple of normal volatility)
av = res[res.measure == "Abnormal volatility [0,+10]"]
fig, ax = plt.subplots(figsize=(9, 3.2))
yl = []
for j, (hz, label) in enumerate(C.HAZARDS.items()):
    for i, s in enumerate(C.SERIES):
        r_ = av[(av.hazard == hz) & (av.series == s)].iloc[0]
        y = j * (len(C.SERIES) + 1) + i
        ax.plot([np.exp(r_.placebo_p05), np.exp(r_.placebo_p95)], [y, y], color=style.INK["grid"], lw=7, solid_capstyle="butt")
        ax.plot(np.exp(r_["mean"]), y, "o", ms=8, color=COL[s])
        yl.append((y, f"{label.split(' /')[0]} · {C.LABELS[s]}"))
ax.axvline(1, color=style.INK["axis"], lw=0.8)
ax.set_yticks([y for y, _ in yl], [t for _, t in yl], fontsize=8)
ax.invert_yaxis()
ax.set_xscale("log")
ticks = [0.5, 0.75, 1, 1.5, 2, 3]
lo, hi = ax.get_xlim()
ax.set_xticks([t for t in ticks if lo <= t <= hi], [f"{t:g}x" for t in ticks if lo <= t <= hi])
ax.xaxis.set_minor_locator(plt.NullLocator())
ax.set_xlabel("Volatility in [0,+10] as a multiple of the month before (dot: events; grey band: same-season placebo, 90%)")
ax.set_title("Abnormal volatility after events")
ax.grid(axis="y", visible=False)
style.save(fig, C.FIG / "02_abnormal_vol.png")

# which events mattered: vol multiple per event and series
for hz, label in C.HAZARDS.items():
    sub = pe[pe.hazard == hz].pivot(index="event", columns="series", values="vol_multiple")[C.SERIES]
    sub = sub.loc[pe[pe.hazard == hz].drop_duplicates("event").sort_values("day0").event]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(sub) + 1.2))
    ax.imshow(np.log(sub.values), cmap=LinearSegmentedColormap.from_list("div", style.DIVERGING),
              vmin=-np.log(4), vmax=np.log(4), aspect="auto")
    for (i, j), v in np.ndenumerate(sub.values):
        ax.text(j, i, f"{v:.1f}x", ha="center", va="center", fontsize=7.5,
                color="white" if abs(np.log(v)) > np.log(2.4) else style.INK["primary"])
    ax.set_xticks(range(len(C.SERIES)), [C.LABELS[s] for s in C.SERIES], fontsize=8)
    ax.set_yticks(range(len(sub)), sub.index, fontsize=8)
    ax.grid(False)
    ax.set_title(f"{C.HAZ_PLURAL[hz]}: volatility in the 10 days after, as a multiple of the month before")
    style.save(fig, C.FIG / f"02_event_heatmap_{hz}.png")

pd.to_pickle(dict(results=res, per_event=pe, paths=paths, events=E), C.DATA_PROC / "eventstudy.pkl")
print("  wrote tables and figures")
