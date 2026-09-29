"""
make_dashboard.py | The static dashboard (docs/index.html), its screenshots, and a copy of the PDF next to it.

Reads only the outputs of pipeline/ (run.sh calls this last). Open docs/index.html in any browser, or publish
it with GitHub Pages from /docs.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

import config as C  # noqa: E402
from climrisk.colors import HAZARD_COLOR, MODEL_COLOR, SERIES_COLOR  # noqa: E402
from climrisk.rr import dashboard, report  # noqa: E402

Dashboard, style_fig = dashboard.Dashboard, dashboard.style_fig
fmt_money, fmt_num, fmt_p, fmt_pct, verdict = report.fmt_money, report.fmt_num, report.fmt_p, report.fmt_pct, report.verdict
rd = lambda n: pd.read_csv(C.TAB / f"{n}.csv")
P = pd.read_pickle(C.DATA_PROC / "prices.pkl")
E = pd.read_pickle(C.DATA_PROC / "events.pkl")
G = pd.read_pickle(C.DATA_PROC / "regimes.pkl")
V = pd.read_pickle(C.DATA_PROC / "var.pkl")
ev, elog, dlog = rd("01_events"), rd("01_events_log"), rd("01_data_log")
es_, pe, paths = rd("02_event_study"), rd("02_event_cars"), rd("02_average_paths")
rg, rpaths = rd("03_regime_summary"), rd("03_regime_paths")
vb, ss, sc = rd("04_var_backtest"), rd("05_stress_scenarios"), rd("05_stress_context")
asof = dlog["last"].min()
AVM = "Abnormal volatility [0,+10]"
prim = es_[es_.primary]
av = prim[prim.measure == AVM].set_index(["hazard", "series"])
mult = lambda v: f"{np.exp(v):.2f}x"
print("Building dashboard")

C.DOCS.mkdir(parents=True, exist_ok=True)
shutil.copy(C.REPORTS / "climate_shock_energy_risk_report.pdf", C.DOCS / "report.pdf")
dx = lambda idx: pd.DatetimeIndex(idx).strftime("%Y-%m-%d").tolist()
ry = lambda a, d=4: [None if not np.isfinite(v) else v for v in np.round(np.asarray(a, float), d).tolist()]
HZ_NAME = {"hurricane": "Hurricanes", "winter": "Winter storms"}
LOG_TICKS = {"WTI": [10, 20, 50, 100], "Brent": [10, 20, 50, 100], "HenryHub": [2, 3, 5, 10, 20, 30]}


def log_axis(fig, s, row=None, col=None, title=None):
    kw = dict(row=row, col=col) if row else {}
    fig.update_yaxes(type="log", tickvals=LOG_TICKS[s], ticktext=[f"{v:g}" for v in LOG_TICKS[s]], title_text=title, **kw)

d = Dashboard("Climate-Shock Energy Risk",
              f"Gulf hurricanes and US winter storms vs oil and gas prices, regime models and VaR · EIA data to {asof}",
              links=[("Report (PDF)", "report.pdf"), ("Models: regime-risk", "https://github.com/n9omi/regime-risk-and-model-validation"),
                     ("GitHub", C.REPO_URL)],
              footer="Data: EIA daily spot prices (FRED or its GitHub mirror); NOAA NHC best tracks (HURDAT2); NOAA NCEI "
                     "billion-dollar disasters. Hypothetical positions; educational project, not investment advice.")


def event_lines(fig, row=None, col=None, since=None):
    for e in E.itertuples():
        if since is not None and e.day0 < pd.Timestamp(since):
            continue
        kw = dict(row=row, col=col) if row else {}
        fig.add_vline(x=e.day0.strftime("%Y-%m-%d"), line_color=HAZARD_COLOR[e.hazard], line_width=1, opacity=0.55, **kw)


# ============================================================================ Overview
t = d.tab("overview", "Overview",
          "When a hurricane crosses the Gulf of Mexico or a winter storm freezes the country, what happens to oil and gas prices, "
          "do standard risk models see it coming, and what would it cost a trading book? Events are chosen by <b>physical rules</b> "
          "(storm tracks, disaster damage), never by what prices did, and every result is compared with <b>random days from the same "
          "season</b>.")
g, oh = av.loc[("winter", "HenryHub")], av.loc[("hurricane", "WTI")]
rgw = rg.set_index(["hazard", "series"]).loc[("winter", "HenryHub")]
vbi = vb.set_index(["position", "model"])
hh_hs, bk_f = vbi.loc[("Long Henry Hub $1mm", "Historical sim")], vbi.loc[("Book", "Filtered HS")]
bk = sc.set_index("position").loc["Book"]
t.kpis([
    ("Events", f"{int(av.loc[('hurricane', 'WTI'), 'n'])} + {int(av.loc[('winter', 'WTI'), 'n'])}", "Gulf hurricanes + winter storms"),
    ("Gas vol after winter storms", mult(g["mean"]), f"vs {mult(g.placebo_mean)} same-season · q {fmt_num(g.q_bh, 3)}",
     "warning" if g.q_bh < 0.1 else "good"),
    ("Oil vol after hurricanes", mult(oh["mean"]), f"vs {mult(oh.placebo_mean)} same-season · p {fmt_p(oh.p_placebo)}"),
    ("Gas regime shift, winter", fmt_num(rgw.mean_shift, 2, signed=True), f"Pr(turbulent) · placebo {fmt_num(rgw.placebo_shift, 2, signed=True)}"),
    ("Plain HS breaches in storms", fmt_pct(hh_hs.window_rate, 1), f"long gas · {fmt_pct(hh_hs.outside_rate, 1)} other days", "critical"),
    ("Worst climate scenario", fmt_money(bk.worst_climate, 0), f"desk book · 10-day VaR {fmt_money(bk.var10, 0)}"),
])
find = pd.DataFrame([
    dict(Question="Do winter storms move gas volatility?", Evidence=f"{mult(g['mean'])} vs {mult(g.placebo_mean)}, placebo p {fmt_p(g.p_placebo)}",
         Answer=verdict(g.q_bh < 0.10, yes="Yes (FDR 10%)", no="Not significant")),
    dict(Question="Do hurricanes move oil volatility?", Evidence=f"{mult(oh['mean'])} vs {mult(oh.placebo_mean)}, placebo p {fmt_p(oh.p_placebo)}",
         Answer=verdict(oh.p_placebo < 0.05, yes="Yes", no="No")),
    dict(Question="Does a real-time regime filter notice winter storms (gas)?", Evidence=f"shift {fmt_num(rgw.mean_shift, 2, signed=True)}, q {fmt_num(rgw.q_bh, 3)}",
         Answer=verdict(rgw.q_bh < 0.10, yes="Yes", no="No")),
    dict(Question="Does plain historical-simulation VaR fail in storms (gas)?", Evidence=f"{fmt_pct(hh_hs.window_rate, 1)} vs {fmt_pct(hh_hs.outside_rate, 1)}, Fisher p {fmt_p(hh_hs.p_fisher)}",
         Answer=verdict(hh_hs.p_fisher < 0.05, yes="Yes", no="No")),
    dict(Question="Does the climate overlay cut storm breaches (book, filtered HS)?",
         Evidence=f"{int(bk_f.window_exceptions)} -> {int(bk_f.overlay_window_exceptions)} breaches for {fmt_pct(bk_f.capital_cost, 1)} more average VaR",
         Answer=verdict(bk_f.overlay_window_exceptions < bk_f.window_exceptions, yes="Yes, cheaply", no="No")),
])
t.table(find, "What the data say", "The detail behind each answer is in the other tabs")
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06)
for i, s in enumerate(["WTI", "HenryHub"], start=1):
    px = P["prices"][s]
    fig.add_scatter(x=dx(px.index), y=ry(px.values, 2), name=C.LABELS[s], line=dict(color=SERIES_COLOR[s], width=1.1), row=i, col=1)
    log_axis(fig, s, i, 1, "$/bbl" if s == "WTI" else "$/MMBtu")
event_lines(fig, 1, 1)
event_lines(fig, 2, 1)
for hz in C.HAZARDS:
    fig.add_scatter(x=[None], y=[None], mode="lines", line=dict(color=HAZARD_COLOR[hz], width=2), name=C.HAZ_PLURAL[hz])
style_fig(fig, 420)
t.chart(fig, "Every event on the price history", "Vertical lines: day 0 of each hurricane (pink) and winter storm (purple)")

# ============================================================================ Events
t = d.tab("events", "Events", "Hurricanes: NOAA best tracks, at hurricane strength inside the northern Gulf box "
          f"({C.GULF_BOX['lat'][0]}-{C.GULF_BOX['lat'][1]}°N, {abs(C.GULF_BOX['lon'][0])}-{abs(C.GULF_BOX['lon'][1])}°W: offshore oil and gas "
          "and the Texas-to-Alabama refineries). Winter storms: NOAA NCEI billion-dollar winter storms and freezes, November to March. "
          "Day 0 is the first trading day on or after the event date.")
t.table(pd.DataFrame({"Hazard": elog.hazard.map(C.HAZARDS), "Source": elog.source, "Kind": elog.source_type,
                      "Data through": elog.data_through, "Events": elog.events}), "Sources", "\"fallback\" = a copy used because NOAA was unreachable")
figs = {}
for hz in C.HAZARDS:
    sub = pe[pe.hazard == hz].pivot(index="event", columns="series", values="vol_multiple")[C.SERIES]
    order = pe[pe.hazard == hz].drop_duplicates("event").sort_values("day0").event
    sub = sub.loc[order]
    z = np.log(sub.values)
    fig = go.Figure(go.Heatmap(z=np.round(z, 3).tolist(), x=[C.LABELS[s] for s in C.SERIES], y=sub.index.tolist(), zmid=0, zmin=-np.log(4),
                               zmax=np.log(4), colorscale=[[0, "#184f95"], [0.33, "#9ec5f4"], [0.5, "#f0efec"], [0.67, "#f3b1ae"], [1, "#b52e2e"]],
                               text=[[f"{v:.1f}x" for v in row] for row in sub.values], texttemplate="%{text}", showscale=False,
                               hovertemplate="%{y} · %{x}: %{text} the month before<extra></extra>"))
    style_fig(fig, 26 * len(sub) + 90, legend=False, unified=False).update_layout(yaxis=dict(autorange="reversed"))
    figs[HZ_NAME[hz]] = fig
t.chart_set("Which events mattered", figs, "Volatility in the 10 trading days after day 0, as a multiple of the month before", half=True)
short_detail = ev.detail.str.replace(r"max (\d+) kt.*", r"max \1 kt", regex=True).str.replace(r"NCEI billion-dollar event, ", "", regex=True)
t.table(pd.DataFrame({"Event": ev.short, "Hazard": ev.hazard.map({"hurricane": "Hurricane", "winter": "Winter"}),
                      "Day 0": ev.day0.str[:10], "Detail": short_detail}),
        "The event list", f"{len(ev)} events since {C.START_DATE[:4]}", half=True)

# ============================================================================ Price response
t = d.tab("response", "Price response", "An event study (MacKinlay, 1997): abnormal returns against each event's own normal return, "
          "and abnormal volatility against the month before. Grey bands: the 90% range of the same statistic on "
          f"{C.N_PLACEBO:,} sets of random days from the same calendar months.")
figs = {}
for hz in C.HAZARDS:
    fig = make_subplots(rows=1, cols=4, subplot_titles=[C.LABELS[s] for s in C.SERIES], horizontal_spacing=0.06)
    for j, s in enumerate(C.SERIES, start=1):
        p = paths[(paths.hazard == hz) & (paths.series == s)]
        fig.add_scatter(x=p.day.tolist(), y=ry(p.placebo_hi, 3), line=dict(width=0), showlegend=False, hoverinfo="skip", row=1, col=j)
        fig.add_scatter(x=p.day.tolist(), y=ry(p.placebo_lo, 3), fill="tonexty", fillcolor="rgba(195,194,183,0.45)", line=dict(width=0),
                        name="Same-season placebo, 90%", showlegend=False, hoverinfo="skip", row=1, col=j)
        fig.add_scatter(x=p.day.tolist(), y=ry(p.mean_car, 3), line=dict(color=SERIES_COLOR[s], width=2), name=C.LABELS[s], showlegend=False,
                        hovertemplate="day %{x}: %{y:.2f}%<extra>" + C.LABELS[s] + "</extra>", row=1, col=j)
        fig.add_vline(x=0, line_dash="dash", line_color="#52514e", line_width=1, row=1, col=j)
    style_fig(fig, 340, unified=False).update_yaxes(title_text="", ticksuffix="%")
    fig.update_layout(margin=dict(t=44))
    figs[HZ_NAME[hz]] = fig
t.chart_set("Average cumulative abnormal return", figs, "Coloured line: the events' average; grey band: 90% range of same-season placebo sets; x axis: trading days from day 0")
fig = go.Figure()
ylab = []
for j, hz in enumerate(C.HAZARDS):
    for s in C.SERIES:
        r_ = av.loc[(hz, s)]
        y = f"{HZ_NAME[hz]} · {C.LABELS[s]}"
        ylab.append(y)
        fig.add_scatter(x=[float(np.exp(r_.placebo_p05)), float(np.exp(r_.placebo_p95))], y=[y, y], mode="lines",
                        line=dict(color="#e1e0d9", width=10), showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=[float(np.exp(r_["mean"]))], y=[y], mode="markers", marker=dict(size=12, color=SERIES_COLOR[s]),
                        showlegend=False, hovertemplate=f"{y}: %{{x:.2f}}x (placebo {np.exp(r_.placebo_mean):.2f}x, p {fmt_p(r_.p_placebo)})<extra></extra>")
fig.add_vline(x=1, line_color="#c3c2b7", line_width=1)
style_fig(fig, 360, legend=False, unified=False).update_layout(xaxis=dict(type="log", title="x the month before"),
                                                              yaxis=dict(autorange="reversed", categoryorder="array", categoryarray=ylab))
t.chart(fig, "Abnormal volatility", "Dots: events; grey: same-season placebo 90% range", half=True)
tt = prim.copy()
t.table(pd.DataFrame({"Hazard": tt.hazard.map(HZ_NAME), "Series": tt.series.map(C.LABELS),
                      "Measure": np.where(tt.measure == AVM, "Volatility", "CAR"),
                      "Events": [mult(m) if x == AVM else f"{m:+.2f}%" for m, x in zip(tt["mean"], tt.measure)],
                      "Placebo p": tt.p_placebo.map(fmt_p), "q": tt.q_bh.map(lambda v: fmt_num(v, 3))}),
        "Primary tests", f"CAR over {C.MAIN_WINDOW.split(' ', 1)[1]}; FDR q across {len(prim)} tests", half=True)

# ============================================================================ Regimes
t = d.tab("regimes", "Regimes", f"regime_risk's two-state Markov-switching model, fitted on {C.START_DATE[:4]}-{C.REGIME_TRAIN_END[:4]} only "
          "and then run forward as a real-time filter (no look-ahead). Does the probability of the turbulent regime jump after events?")
figs = {}
for s in ["HenryHub", "WTI", "Brent", "Brent-WTI"]:                  # gas first: that is where the storms show up
    pr = G["prob"][s].loc[C.REGIME_TRAIN_END:]
    lvl = P["prices"][s].loc[pr.index] if s in P["prices"] else (1 + P["rets"][s].loc[pr.index] / 100).cumprod() * 100
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.05)
    fig.add_scatter(x=dx(lvl.index), y=ry(lvl.values, 3), line=dict(color=SERIES_COLOR[s], width=1.1),
                    name="Price" if s in P["prices"] else "Spread index", row=1, col=1)
    fig.add_scatter(x=dx(pr.index), y=ry(pr.values, 3), line=dict(color="#52514e", width=1), fill="tozeroy",
                    fillcolor="rgba(243,217,207,0.8)", name="Pr(turbulent), real time", row=2, col=1)
    event_lines(fig, 1, 1, since=C.REGIME_TRAIN_END)
    if s in P["prices"]:
        log_axis(fig, s, 1, 1)
    fig.update_yaxes(range=[0, 1], row=2, col=1)
    style_fig(fig, 430)
    figs[C.LABELS[s]] = fig
t.chart_set("Real-time regime probability and events", figs, "Vertical lines: hurricanes (pink), winter storms (purple)")
fig = make_subplots(rows=1, cols=2, subplot_titles=["Henry Hub · winter storms", "WTI · hurricanes"])
for j, (hz, s) in enumerate([("winter", "HenryHub"), ("hurricane", "WTI")], start=1):
    p = rpaths[(rpaths.hazard == hz) & (rpaths.series == s)]
    fig.add_scatter(x=p.day.tolist(), y=ry(p.placebo_hi, 3), line=dict(width=0), showlegend=False, hoverinfo="skip", row=1, col=j)
    fig.add_scatter(x=p.day.tolist(), y=ry(p.placebo_lo, 3), fill="tonexty", fillcolor="rgba(195,194,183,0.45)", line=dict(width=0),
                    name="Placebo 90%", showlegend=False, hoverinfo="skip", row=1, col=j)
    fig.add_scatter(x=p.day.tolist(), y=ry(p.prob, 3), line=dict(color=SERIES_COLOR[s], width=2), name=C.LABELS[s], showlegend=False,
                    row=1, col=j)
    fig.add_vline(x=0, line_dash="dash", line_color="#52514e", line_width=1, row=1, col=j)
style_fig(fig, 330, unified=False).update_yaxes(range=[0, 1])
fig.update_layout(margin=dict(t=44))
t.chart(fig, "Average Pr(turbulent) around events", "Line: events; grey: same-season placebo 90%; x: trading days from day 0", half=True)
t.table(pd.DataFrame({"Hazard": rg.hazard.map(HZ_NAME), "Series": rg.series.map(C.LABELS), "Shift": rg.mean_shift.map(lambda v: fmt_num(v, 2, signed=True)),
                      "Placebo": rg.placebo_shift.map(lambda v: fmt_num(v, 2, signed=True)), "q": rg.q_bh.map(lambda v: fmt_num(v, 3))}),
        "Shift in Pr(turbulent)", f"Days +1..+10 minus -15..-6; events after {C.REGIME_TRAIN_END[:4]}", half=True)

# ============================================================================ VaR
t = d.tab("var", "VaR in storms", f"99% one-day VaR forecast every day since {C.BACKTEST_START[:4]} with data to the day before. "
          f"Storm windows run from day {C.RISK_WIN[0]} to +{C.RISK_WIN[1]}. The climate overlay scales VaR inside a window by k, learned "
          "only from earlier storms of the same kind.")
figs = {}
for pname in C.POSITIONS:
    dd = V["paths"][(pname, "Filtered HS")]
    fig = go.Figure()
    for col, hz in (("in_hurricane", "hurricane"), ("in_winter", "winter")):
        m = dd[col].values.astype(int)
        edges = np.flatnonzero(np.diff(np.r_[0, m, 0]))
        for a, b in zip(edges[::2], edges[1::2]):
            fig.add_vrect(x0=dd.index[a].strftime("%Y-%m-%d"), x1=dd.index[min(b, len(dd) - 1)].strftime("%Y-%m-%d"),
                          fillcolor=HAZARD_COLOR[hz], opacity=0.18, line_width=0)
    fig.add_scatter(x=dx(dd.index), y=ry(dd.pnl / 1e3, 1), mode="lines", line=dict(color="#c3c2b7", width=0.7), name="Daily P&L ($k)")
    fig.add_scatter(x=dx(dd.index), y=ry(-dd["var"] / 1e3, 1), line=dict(color=MODEL_COLOR["Filtered HS"], width=1.2), name="-VaR, filtered HS")
    fig.add_scatter(x=dx(dd.index), y=ry(-dd.var_overlay / 1e3, 1), line=dict(color="#0b0b0b", width=1, dash="dash"), name="-VaR with overlay")
    ex = dd[dd.exc]
    fig.add_scatter(x=dx(ex.index), y=ry(ex.pnl / 1e3, 1), mode="markers", marker=dict(symbol="triangle-down", size=8, color="#d03b3b"), name="Breach")
    style_fig(fig, 380, unified=False).update_layout(yaxis_title="$ thousands")
    figs[pname] = fig
t.chart_set("P&L, VaR and breaches", figs, "Shaded: hurricane (pink) and winter-storm (purple) risk windows")
fig = go.Figure()
for m in MODEL_COLOR:
    sub = vb[vb.model == m]
    fig.add_bar(y=sub.position + " · " + m, x=(sub.window_rate * 100).round(2), orientation="h", marker_color=MODEL_COLOR[m], name=m,
                hovertemplate="%{y}: %{x:.2f}% in storm windows<extra></extra>")
fig.add_vline(x=C.VAR_P * 100, line_color="#d03b3b", line_dash="dash", annotation_text="1% target", annotation_position="bottom right")
style_fig(fig, 360, unified=False).update_layout(xaxis_title="Breach rate inside storm windows (%)", yaxis=dict(autorange="reversed"), bargap=0.3)
t.chart(fig, "Breach rate inside storm windows", "Target 1%; other days are near 1% for every model", half=True)
t.table(pd.DataFrame({"Position": vb.position.str.replace(" $1mm", ""), "Model": vb.model,
                      "Storm": vb.window_rate.map(lambda v: fmt_pct(v, 1)), "Other": vb.outside_rate.map(lambda v: fmt_pct(v, 1)),
                      "Fisher p": vb.p_fisher.map(fmt_p),
                      "Overlay": [f"{a} -> {b}" for a, b in zip(vb.window_exceptions, vb.overlay_window_exceptions)],
                      "Cost": vb.capital_cost.map(lambda v: fmt_pct(v, 1))}),
        "Backtest and overlay", "Overlay: storm-window breaches before -> after; cost: extra average VaR", half=True)

# ============================================================================ Stress
t = d.tab("stress", "Stress tests", f"Each event's actual {C.STRESS_WIN[1] - C.STRESS_WIN[0] + 1}-day price moves (day {C.STRESS_WIN[0]} to "
          f"+{C.STRESS_WIN[1]}) replayed on today's positions. The book is " +
          ", ".join(f"{'+' if v > 0 else '−'}${abs(v) / 1e6:g}mm {k}" for k, v in C.BOOK.items()) + ".")
figs = {}
for pname in C.POSITIONS:
    b = ss.sort_values(pname)
    v10 = sc.set_index("position").loc[pname, "var10"]
    fig = go.Figure(go.Bar(y=b.event.tolist(), x=ry(b[pname] / 1e3, 1), orientation="h",
                           marker_color=[HAZARD_COLOR[h] for h in b.hazard],
                           customdata=np.c_[b.WTI_pct.round(1), b.Brent_pct.round(1), b.HenryHub_pct.round(1)],
                           hovertemplate="%{y}: %{x:,.0f}k<br>WTI %{customdata[0]}% · Brent %{customdata[1]}% · HH %{customdata[2]}%<extra></extra>"))
    fig.add_vline(x=-v10 / 1e3, line_color="#d03b3b", line_dash="dash", annotation_text="10-day 99% VaR", annotation_position="bottom right")
    style_fig(fig, 26 * len(b) + 90, legend=False, unified=False).update_layout(xaxis_title="P&L ($ thousands)", yaxis=dict(autorange="reversed"))
    figs[pname] = fig
t.chart_set("P&L if each storm happened today", figs, "Pink: hurricanes, purple: winter storms", half=True)
t.table(pd.DataFrame({"Position": sc.position.str.replace(" $1mm", ""), "10-day VaR": sc.var10.map(lambda v: fmt_money(v, 0)),
                      "Worst climate": sc.worst_climate.map(lambda v: fmt_money(v, 0)), "Event": sc.worst_climate_event,
                      "Beyond VaR": [f"{a}/{b}" for a, b in zip(sc.climate_scenarios_beyond_var, sc.scenarios)],
                      "Worst 13 days, any cause": sc.worst_any.map(lambda v: fmt_money(v, 0))}),
        "Scenario losses in context", "Climate matters, but it is not the biggest tail for these books", half=True)

out = d.write(C.DOCS)
print(f"  wrote {out}")
shots = d.screenshot(C.DOCS, keys=["overview", "events", "response", "regimes", "var", "stress"])
print(f"  {len(shots)} screenshots")
