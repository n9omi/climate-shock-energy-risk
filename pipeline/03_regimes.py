"""
03_regimes.py | Step 3: does a Markov-switching model flag the storms as a switch to the turbulent regime?

regime_risk.regimes fits a 2-state model r_t | s_t ~ N(mu_s, sigma_s^2) with a Markov chain for s_t, on the
training years only (to REGIME_TRAIN_END). The fitted model then runs as a real-time Hamilton filter over the
rest of the sample: Pr(turbulent on day t | returns up to day t), with no re-fitting and no look-ahead.
Only events after the training period are scored:
    shift     = mean Pr(turbulent) over [+1,+10]  -  mean over [-15,-6]
    detection = the filter was below 1/2 before the event and crossed 1/2 within [0,+10]
The same numbers on month-matched placebo dates say what an ordinary day in the same season looks like.
Outputs: tables/03_*.csv, figures/03_*.png, data/processed/regimes.pkl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402
from climrisk import eventstudy as es  # noqa: E402
from climrisk.colors import HAZARD_COLOR, SERIES_COLOR  # noqa: E402
from climrisk.rr import regimes, style  # noqa: E402

style.apply()
P = pd.read_pickle(C.DATA_PROC / "prices.pkl")
E = pd.read_pickle(C.DATA_PROC / "events.pkl")
R = P["rets"][C.SERIES]
n = len(R)
train = R.index <= pd.Timestamp(C.REGIME_TRAIN_END)
B0, B1 = C.REGIME_WIN["before"]
A0, A1 = C.REGIME_WIN["after"]
rel = np.arange(C.PATH_WIN[0], C.PATH_WIN[1] + 1)
print(f"Step 3 | regimes (fitted to {C.REGIME_TRAIN_END[:4]}, then filtered in real time)")

first_test = int(np.argmax(~train))
post = E[(E.pos >= first_test + abs(B0)) & (E.pos + max(A1, C.PATH_WIN[1]) < n)].reset_index(drop=True)
pool = es.placebo_pool(R.index, n, E.pos.values, C.PLACEBO_BUFFER, (-abs(B0), 0), C.PATH_WIN)
pool = {m: v[v >= first_test + abs(C.PATH_WIN[0])] for m, v in pool.items()}

fit_rows, ev_rows, summ, paths, prob = [], [], [], [], {}
for s in C.SERIES:
    y = R[s].values
    res = regimes.fit(y[train], K=2, seed=C.SEED)
    filt, _ = regimes.filter_fixed(y, res)
    p_hi = filt[:, 1]
    prob[s] = pd.Series(p_hi, index=R.index)
    ann = np.sqrt(252) * res.sigma
    fit_rows.append(dict(series=s, calm_vol_ann=ann[0], turbulent_vol_ann=ann[1], calm_days=res.durations[0],
                         turbulent_days=res.durations[1], share_turbulent_test=float((p_hi[~train] > 0.5).mean()),
                         converged=res.converged))
    all_pos = np.arange(n)

    def stats_at(pos):
        pos = np.asarray(pos, int)
        before = p_hi[pos[..., None] + np.arange(B0, B1 + 1)].mean(-1)
        after = p_hi[pos[..., None] + np.arange(A0, A1 + 1)].mean(-1)
        peak = p_hi[pos[..., None] + np.arange(0, A1 + 1)].max(-1)
        return after - before, (before < 0.5) & (peak >= 0.5)

    for hz, label in C.HAZARDS.items():
        ev = post[post.hazard == hz]
        if len(ev) < 3:
            continue
        shift, det = stats_at(ev.pos.values)
        draws = es.placebo_draws(ev.month.values, pool, C.N_PLACEBO, seed=C.SEED + 3)
        p_shift, p_det = stats_at(draws)
        pl_shift, pl_det = p_shift.mean(axis=1), p_det.mean(axis=1)
        summ.append(dict(hazard=hz, series=s, n=len(ev), mean_shift=float(shift.mean()), placebo_shift=float(pl_shift.mean()),
                         p_shift=es.placebo_p(float(shift.mean()), pl_shift), detected_share=float(det.mean()),
                         placebo_detected_share=float(pl_det.mean()), p_detected=es.placebo_p(float(det.mean()), pl_det)))
        for i, e in enumerate(ev.itertuples()):
            ev_rows.append(dict(event=e.short, hazard=hz, day0=e.day0.date(), series=s, before=float(p_hi[e.pos + np.arange(B0, B1 + 1)].mean()),
                                after=float(p_hi[e.pos + np.arange(A0, A1 + 1)].mean()), shift=float(shift[i]), detected=bool(det[i])))
        pth = p_hi[ev.pos.values[:, None] + rel[None, :]].mean(axis=0)
        pl = p_hi[draws[..., None] + rel].mean(axis=1)
        paths.append(pd.DataFrame(dict(hazard=hz, series=s, day=rel, prob=pth, placebo_lo=np.quantile(pl, 0.05, axis=0),
                                       placebo_hi=np.quantile(pl, 0.95, axis=0))))

fits = pd.DataFrame(fit_rows)
fits.to_csv(C.TAB / "03_regime_fit.csv", index=False)
summ = pd.DataFrame(summ)
summ["q_bh"] = es.bh_qvalues(summ.p_shift.values)
summ.to_csv(C.TAB / "03_regime_summary.csv", index=False)
evr = pd.DataFrame(ev_rows)
evr.to_csv(C.TAB / "03_regime_events.csv", index=False)
paths = pd.concat(paths, ignore_index=True)
paths.to_csv(C.TAB / "03_regime_paths.csv", index=False)
print(fits.round(2).to_string(index=False))
print(summ.round(3).to_string(index=False))

# --- figures ------------------------------------------------------------------------------------------
COL = SERIES_COLOR
fig, axes = plt.subplots(2, 4, figsize=(9, 4.6), sharex=True, sharey=True)
for r_, (hz, label) in enumerate(C.HAZARDS.items()):
    for c_, s in enumerate(C.SERIES):
        ax = axes[r_, c_]
        p = paths[(paths.hazard == hz) & (paths.series == s)]
        if p.empty:
            ax.set_visible(False)
            continue
        ax.fill_between(p.day, p.placebo_lo, p.placebo_hi, color=style.INK["grid"], lw=0, label="Placebo, 90%")
        ax.plot(p.day, p.prob, color=COL[s], lw=1.6, label="Events")
        ax.axvline(0, color=style.INK["secondary"], lw=0.8, ls="--")
        ax.set_ylim(0, 1)
        if r_ == 0:
            ax.set_title(C.LABELS[s], fontsize=9)
        if c_ == 0:
            ax.set_ylabel(f"{label.split(' /')[0]}\nPr(turbulent)", fontsize=8.5)
        if r_ == 1:
            ax.set_xlabel("Trading days from day 0", fontsize=8)
axes[0, 0].legend(loc="upper left", fontsize=7)
fig.suptitle(f"Real-time probability of the turbulent regime around events after {C.REGIME_TRAIN_END[:4]}",
             x=0.01, ha="left", fontweight="bold", fontsize=10.5)
fig.tight_layout()
style.save(fig, C.FIG / "03_regime_paths.png")

# Henry Hub with its turbulent regime shaded and every event marked
s = "HenryHub"
px = P["prices"][s].loc[R.index[first_test]:]
ph = prob[s].loc[px.index]
fig, ax = plt.subplots(figsize=(9, 3.4))
turb = (ph > 0.5).values
edges = np.flatnonzero(np.diff(np.r_[0, turb.astype(int), 0]))
for a, b in zip(edges[::2], edges[1::2]):
    ax.axvspan(px.index[a], px.index[min(b, len(px) - 1)], color=style.INK["grid"], lw=0)
ax.plot(px.index, px.values, color=COL[s], lw=0.9)
for e in E[E.day0 >= px.index[0]].itertuples():
    ax.axvline(e.day0, color=HAZARD_COLOR[e.hazard], lw=1.1, alpha=0.95)
ax.set_yscale("log")
ax.set_yticks([2, 3, 5, 10, 20, 30], ["2", "3", "5", "10", "20", "30"])
ax.yaxis.set_minor_locator(plt.NullLocator())
ax.set_ylabel("$/MMBtu (log scale)")
ax.set_title("Henry Hub: turbulent regime (grey) and events (pink: hurricanes, purple: winter storms)")
style.save(fig, C.FIG / "03_henryhub_regimes.png")
pd.to_pickle(dict(prob=pd.DataFrame(prob), fits=fits, summary=summ, events=evr, paths=paths), C.DATA_PROC / "regimes.pkl")
print("  wrote tables and figures")
