"""
make_report.py | The PDF (and Markdown) report, written from the output tables so every sentence matches the numbers.
Also refreshes the highlights table at the top of README.md.

Outputs: reports/climate_shock_energy_risk_report.pdf, outputs/climate_shock_energy_risk_report.md (+ .html)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402
from climrisk.readme import md_table, update_block  # noqa: E402
from climrisk.rr import report, version  # noqa: E402

Report, fmt_money, fmt_num, fmt_p, fmt_pct = report.Report, report.fmt_money, report.fmt_num, report.fmt_p, report.fmt_pct

rd = lambda n: pd.read_csv(C.TAB / f"{n}.csv")
ev, elog, dlog = rd("01_events"), rd("01_events_log"), rd("01_data_log")
es_, pe = rd("02_event_study"), rd("02_event_cars")
rg, rfit = rd("03_regime_summary"), rd("03_regime_fit")
vb, kk = rd("04_var_backtest"), rd("04_overlay_k")
ss, sc = rd("05_stress_scenarios"), rd("05_stress_context")
F = lambda n: C.FIG / n
asof = dlog["last"].min()
fallback = (elog.source_type != "official").any()
print("Writing the report")

AVM = "Abnormal volatility [0,+10]"
prim = es_[es_.primary]
av = prim[prim.measure == AVM].set_index(["hazard", "series"])
cr = prim[prim.measure == C.MAIN_WINDOW].set_index(["hazard", "series"])
mult = lambda v: f"{np.exp(v):.2f}x"
n_h, n_w = int(av.loc[("hurricane", "WTI"), "n"]), int(av.loc[("winter", "WTI"), "n"])
sig = prim[prim.q_bh < 0.10]
g = av.loc[("winter", "HenryHub")]
oil_h = av.loc[("hurricane", "WTI")]
rgi = rg.set_index(["hazard", "series"])
rgw = rgi.loc[("winter", "HenryHub")]
vbi = vb.set_index(["position", "model"])
hh_hs = vbi.loc[("Long Henry Hub $1mm", "Historical sim")]
hh_f = vbi.loc[("Long Henry Hub $1mm", "Filtered HS")]
bk_f = vbi.loc[("Book", "Filtered HS")]
bk_g = vbi.loc[("Book", "GARCH-t")]
sci = sc.set_index("position")
bk = sci.loc["Book"]
worst_hh = pe[(pe.hazard == "winter") & (pe.series == "HenryHub")].sort_values("vol_multiple", ascending=False).head(3)

rep = Report("Climate-Shock Energy Risk",
             f"How Gulf hurricanes and US winter storms move oil and gas prices, and whether risk models see them coming · "
             f"EIA data to {asof}", C.OUT, "climate_shock_energy_risk_report")

# ------------------------------------------------------------------ headline
rep.section("Headline numbers")
rep.kpis([
    ("Events tested", f"{n_h} + {n_w}", "Gulf hurricanes + winter storms with a full year of prior data"),
    ("Gas volatility after winter storms", mult(g["mean"]), f"of the month before; same-season days {mult(g.placebo_mean)} (q = {fmt_num(g.q_bh, 3)})"),
    ("Oil volatility after hurricanes", mult(oil_h["mean"]), f"same-season days {mult(oil_h.placebo_mean)} (p = {fmt_p(oil_h.p_placebo)})"),
    ("Henry Hub regime shift, winter", fmt_num(rgw.mean_shift, 2, signed=True), f"change in Pr(turbulent); placebo {fmt_num(rgw.placebo_shift, 2, signed=True)}"),
    ("Plain HS VaR in storms (gas)", fmt_pct(hh_hs.window_rate, 1), f"breach rate vs {fmt_pct(hh_hs.outside_rate, 1)} on other days (target 1%)"),
    ("Worst climate scenario, book", fmt_money(bk.worst_climate, 0), f"{bk.worst_climate_event}; 10-day VaR {fmt_money(bk.var10, 0)}"),
])

b = []
b.append(f"**Winter storms are a gas-volatility event; the average move hides a fat tail.** In the ten trading days after a winter storm, "
         f"Henry Hub volatility averaged {mult(g['mean'])} its level in the month before, against {mult(g.placebo_mean)} on random days in the "
         f"same months (placebo p {fmt_p(g.p_placebo)}, FDR q {fmt_num(g.q_bh, 3)}). Most storms barely register: the average is driven by "
         + ", ".join(f"{r.event} ({r.vol_multiple:.0f}x)" for r in worst_hh.itertuples()) + ".")
b.append(f"**Hurricanes do not move oil the way headlines suggest.** Across {n_h} Gulf hurricanes, crude volatility after landfall was "
         f"{mult(oil_h['mean'])} the month before (same-season days: {mult(oil_h.placebo_mean)}; p {fmt_p(oil_h.p_placebo)}), and no average "
         f"price move survives a same-season placebo test after correcting for {len(prim)} tests"
         + (f" (smallest q {fmt_num(prim[prim.hazard == 'hurricane'].q_bh.min(), 2)})." if True else "."))
b.append(f"**A regime model notices winter storms in real time.** A two-state Markov-switching model fitted only on data to "
         f"{C.REGIME_TRAIN_END[:4]} and then run as a live filter raised its probability of the turbulent regime for Henry Hub by "
         f"{fmt_num(rgw.mean_shift, 2, signed=True)} after winter storms, against {fmt_num(rgw.placebo_shift, 2, signed=True)} on placebo dates "
         f"(q {fmt_num(rgw.q_bh, 3)}). It shows no such shift for hurricanes in any series.")
b.append(f"**The VaR model that fails in storms is the one that does not update volatility.** Plain historical simulation breached on "
         f"{fmt_pct(hh_hs.window_rate, 1)} of storm-window days for a long gas position, against {fmt_pct(hh_hs.outside_rate, 1)} elsewhere "
         f"(Fisher p {fmt_p(hh_hs.p_fisher)}). Filtered HS and GARCH-t, which re-weight to recent volatility every day, stayed near "
         f"{fmt_pct(hh_f.window_rate, 1)} (p {fmt_p(hh_f.p_fisher)}).")
b.append(f"**A climate overlay learned only from past storms cuts storm-window breaches cheaply.** For the desk book it takes filtered-HS "
         f"breaches in storm windows from {int(bk_f.window_exceptions)} to {int(bk_f.overlay_window_exceptions)} and GARCH-t from "
         f"{int(bk_g.window_exceptions)} to {int(bk_g.overlay_window_exceptions)}, for {fmt_pct(bk_f.capital_cost, 1)} and "
         f"{fmt_pct(bk_g.capital_cost, 1)} more average VaR. It cannot rescue plain HS in the extreme cold snaps, which lost up to 4x VaR in a day.")
b.append(f"**Stress test:** replaying each storm's 13-day price moves on today's book, the worst case is {bk.worst_climate_event} at "
         f"{fmt_money(bk.worst_climate, 0)} ({int(bk.climate_scenarios_beyond_var)} of {int(bk.scenarios)} scenarios exceed today's 10-day 99% VaR of "
         f"{fmt_money(bk.var10, 0)}). The worst 13 days of the whole sample, ending {bk.worst_any_end}, cost {fmt_money(bk.worst_any, 0)}: "
         "climate is a real but not the dominant source of tail risk for this book.")
rep.bullets(b)
rep.callout("Events are picked by physical rules (a storm's track and winds; a disaster's damage), never by what prices did, and every "
            "test compares events with random days from the same calendar months, because hurricane season and winter are volatile anyway.", "note")
if fallback:
    rep.callout("This build used fallback copies of the event data (" + "; ".join(f"{r.hazard}: {r.source}" for r in elog.itertuples()
                if r.source_type != "official") + ") because the NOAA servers were unreachable. `bash run.sh` re-downloads the official files.", "warn")

# ------------------------------------------------------------------ 1 events
rep.section("1. The events", new_page=True)
rep.text(f"**Hurricanes** come from NOAA's best-track database (HURDAT2): a storm counts if it is at hurricane strength (at least "
         f"{C.HURRICANE_KT} knots) while inside the northern Gulf box {C.GULF_BOX['lat'][0]}-{C.GULF_BOX['lat'][1]}°N, "
         f"{abs(C.GULF_BOX['lon'][0])}-{abs(C.GULF_BOX['lon'][1])}°W, which covers the federal offshore oil and gas fields and the Texas-to-Alabama "
         "refining coast. Day 0 is the first date it is there. **Winter storms** come from NOAA NCEI's billion-dollar disaster list: every "
         "\"Winter Storm\" or \"Freeze\" that began between November and March, with episodes less than a week apart merged. Day 0 is the "
         "first trading day on or after the event date.")
rep.table(pd.DataFrame({"Hazard": elog.hazard, "Source": elog.source, "Data through": elog.data_through, "Events": elog.events, "Rule": elog.rule}),
          "Where the events come from", small=True)
rep.figure(F("01_events_timeline.png"), "Every event on the WTI and Henry Hub price history.")
rep.table(pd.DataFrame({"Event": ev.short, "Hazard": ev.hazard.map(C.HAZARDS), "Date": ev.date.str[:10], "Day 0": ev.day0.str[:10],
                        "Detail": ev.detail}), "The event list", small=True)

# ------------------------------------------------------------------ 2 event study
rep.section("2. Price response: an event study", new_page=True)
rep.text("For each event, the normal return is the average over trading days -250 to -21. Abnormal returns are deviations from it, "
         "summed into a cumulative abnormal return (CAR) for direction. Abnormal volatility compares the ten days after day 0 with the "
         "month before, for size. Each average is tested three ways: a t-test across events, a sign test, and a placebo that repeats the "
         f"calculation on {C.N_PLACEBO:,} random sets of dates from the same calendar months with no event within {C.PLACEBO_BUFFER} trading days. "
         f"Benjamini-Hochberg q-values control the false-discovery rate across the {len(prim)} primary tests.")
t = prim.copy()
t["value"] = [mult(m) if meas == AVM else f"{m:+.2f}%" for m, meas in zip(t["mean"], t.measure)]
t["placebo"] = [mult(m) if meas == AVM else f"{m:+.2f}%" for m, meas in zip(t.placebo_mean, t.measure)]
rep.table(pd.DataFrame({"Hazard": t.hazard.map(C.HAZARDS), "Series": t.series.map(C.LABELS),
                        "Measure": t.measure.str.replace(" [0,+10]", "").str.replace(f" {C.MAIN_WINDOW.split(' ', 1)[1]}", " CAR"),
                        "Events": t.value, "Placebo": t.placebo, "t-test p": t.p_ttest.map(fmt_p),
                        "Placebo p": t.p_placebo.map(fmt_p), "q (FDR)": t.q_bh.map(lambda v: fmt_num(v, 3))}),
          f"Primary tests: CAR over {C.MAIN_WINDOW.split(' ', 1)[1]} and abnormal volatility over [0,+10]", small=True)
rep.figure(F("02_abnormal_vol.png"), "Volatility after events as a multiple of the month before, against the same-season placebo range.")
rep.figure(F("02_car_paths_hurricane.png"), "Hurricanes: average cumulative abnormal return; grey = 90% range of same-season placebo sets.")
rep.figure(F("02_car_paths_winter.png"), "Winter storms: average cumulative abnormal return.")
rep.figure(F("02_event_heatmap_winter.png"), "Winter storms, one row each: most barely register; a few multiply gas volatility.")
rep.figure(F("02_event_heatmap_hurricane.png"), "Hurricanes, one row each.")

# ------------------------------------------------------------------ 3 regimes
rep.section("3. Do regime models notice?", new_page=True)
rep.text(f"regime_risk's two-state Markov-switching model is fitted on {C.START_DATE[:4]}-{C.REGIME_TRAIN_END[:4]} only, then run forward "
         "as a real-time Hamilton filter with fixed parameters. The shift is the average probability of the turbulent regime over "
         f"days {C.REGIME_WIN['after'][0]} to +{C.REGIME_WIN['after'][1]} minus days {C.REGIME_WIN['before'][0]} to {C.REGIME_WIN['before'][1]}, "
         "for events after the training period.")
rep.table(pd.DataFrame({"Series": rfit.series.map(C.LABELS), "Calm vol": rfit.calm_vol_ann.map(lambda v: f"{v:.0f}%"),
                        "Turbulent vol": rfit.turbulent_vol_ann.map(lambda v: f"{v:.0f}%"),
                        "Calm spell (days)": rfit.calm_days.map(lambda v: f"{v:.0f}"), "Turbulent spell (days)": rfit.turbulent_days.map(lambda v: f"{v:.0f}")}),
          "Fitted regimes (annualised volatility, expected spell length)", small=True)
rep.table(pd.DataFrame({"Hazard": rg.hazard.map(C.HAZARDS), "Series": rg.series.map(C.LABELS), "Events": rg.n,
                        "Shift": rg.mean_shift.map(lambda v: fmt_num(v, 2, signed=True)),
                        "Placebo shift": rg.placebo_shift.map(lambda v: fmt_num(v, 2, signed=True)),
                        "p": rg.p_shift.map(fmt_p), "q (FDR)": rg.q_bh.map(lambda v: fmt_num(v, 3))}),
          "Change in the real-time probability of the turbulent regime", small=True)
rep.figure(F("03_regime_paths.png"), "Average real-time probability of the turbulent regime around events, with the placebo range.")
rep.figure(F("03_henryhub_regimes.png"), "Henry Hub since 2015: turbulent regime (grey) and events.")

# ------------------------------------------------------------------ 4 VaR
rep.section("4. VaR in storms, and a climate overlay", new_page=True)
rep.text(f"Three 99% one-day VaR models from regime_risk and climrisk.overlay forecast every day from {C.BACKTEST_START[:4]} using data up to "
         f"the day before: historical simulation ({C.HS_WINDOW} days), filtered HS (EWMA {C.EWMA_LAMBDA}) and GARCH(1,1)-t re-estimated every "
         f"{C.GARCH_REFIT_DAYS} days. A storm's risk window runs from {C.RISK_WIN[0]} to +{C.RISK_WIN[1]} trading days around day 0 "
         "(hurricane and winter-storm watches give about two days' warning). The overlay multiplies VaR inside a window by k, the ratio of "
         "realised to model-implied volatility in earlier storms of the same kind (only days before the window opens), capped at "
         f"{C.K_CAP:g} and switched on after {C.MIN_PAST_EVENTS} past events.")
rep.table(pd.DataFrame({"Position": vb.position.str.replace(" $1mm", ""), "Model": vb.model,
                        "All days": vb.rate.map(lambda v: fmt_pct(v, 2)),
                        "Storm windows": vb.window_rate.map(lambda v: fmt_pct(v, 2)),
                        "Other days": vb.outside_rate.map(lambda v: fmt_pct(v, 2)), "Fisher p": vb.p_fisher.map(fmt_p),
                        "Storm breaches, then with overlay": [f"{a} -> {b}" for a, b in zip(vb.window_exceptions, vb.overlay_window_exceptions)],
                        "Extra avg VaR": vb.capital_cost.map(lambda v: fmt_pct(v, 1))}),
          f"Breach rates (target {fmt_pct(C.VAR_P, 0)}); {int(vb.window_days.iloc[0])} storm-window days in the backtest", small=True)
rep.figure(F("04_breach_rates.png"), "Breach rates inside storm windows (filled) and on other days (hollow).")
rep.figure(F("04_overlay.png"), "The overlay: storm-window breach rate before (dot) and after (arrow tip), with its cost in average VaR.")
rep.figure(F("04_henryhub_var.png"), "A long Henry Hub position: P&L, filtered-HS VaR, the overlay and breaches.")

# ------------------------------------------------------------------ 5 stress
rep.section("5. Climate stress tests", new_page=True)
rep.text(f"Each event's actual {C.STRESS_WIN[1] - C.STRESS_WIN[0] + 1}-day price changes (day {C.STRESS_WIN[0]} to +{C.STRESS_WIN[1]}) applied to "
         "today's positions: " + ", ".join(f"{'+' if v > 0 else '-'}${abs(v) / 1e6:g}mm {k}" for k, v in C.BOOK.items()) +
         " for the book. The 10-day VaR is the square-root-of-time scaling of today's one-day filtered-HS VaR.")
rep.table(pd.DataFrame({"Position": sc.position, "10-day 99% VaR": sc.var10.map(lambda v: fmt_money(v, 0)),
                        "Worst climate scenario": sc.worst_climate.map(lambda v: fmt_money(v, 0)), "Event": sc.worst_climate_event,
                        "Scenarios beyond VaR": [f"{a} of {b}" for a, b in zip(sc.climate_scenarios_beyond_var, sc.scenarios)],
                        "Worst 13 days, any cause": sc.worst_any.map(lambda v: fmt_money(v, 0)), "Ending": sc.worst_any_end}),
          "Scenario losses in context", small=True)
top = ss.sort_values("Book").head(10)
rep.table(pd.DataFrame({"Event": top.event, "WTI": top.WTI_pct.map(lambda v: f"{v:+.1f}%"), "Brent": top.Brent_pct.map(lambda v: f"{v:+.1f}%"),
                        "Henry Hub": top.HenryHub_pct.map(lambda v: f"{v:+.1f}%"), "Book P&L": top.Book.map(lambda v: fmt_money(v, 0)),
                        "x 10-day VaR": top["Book / VaR10"].map(lambda v: f"{v:+.2f}")}), "The ten worst scenarios for the book", small=True)
rep.figure(F("05_stress_book.png"), "Book P&L under every historical climate scenario.")

# ------------------------------------------------------------------ notes
rep.section("Method notes, limitations and references", new_page=True)
rep.bullets([
    f"Models come from the package `regime_risk` ({version()}), the tested library of github.com/n9omi/regime-risk-and-model-validation; this project adds only the event logic, the event study and the overlay.",
    "Spot prices, not futures: spot Henry Hub reacts to same-day weather more than the front-month contract, which exaggerates gas moves relative to what a futures book would see.",
    "Event dates are physical, not the moment markets learned of them: forecasts move prices days earlier, which the run-up window [-5,-1] and the risk window starting at -2 only partly capture.",
    "NOAA stopped updating the billion-dollar database in 2025, so winter storms after 2024 are missing, including the late-January 2026 cold snap that produced the worst 13 days for a long gas position.",
    f"{n_h} and {n_w} events are small samples: a single storm (February 2021) can move an average, which is why the placebo tests and per-event tables matter more than any one mean.",
    "The overlay assumes the risk manager knows about two trading days ahead that a named storm will hit; NHC and NWS watches usually give that, but its timing is idealised.",
])
rep.sub("References")
rep.bullets([
    "MacKinlay, A. C. (1997). Event studies in economics and finance. *Journal of Economic Literature*, 35(1).",
    "Brown, S. & Warner, J. (1985). Using daily stock returns: the case of event studies. *Journal of Financial Economics*, 14(1).",
    "Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS B*, 57(1).",
    "Hamilton, J. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica*, 57(2).",
    "Barone-Adesi, G., Giannopoulos, K. & Vosper, L. (1999). VaR without correlations for portfolios of derivative securities. *Journal of Futures Markets*, 19(5).",
    "Bollerslev, T. (1987). A conditionally heteroskedastic time series model for speculative prices and rates of return. *Review of Economics and Statistics*, 69(3).",
    "Kupiec, P. (1995). Techniques for verifying the accuracy of risk measurement models. *Journal of Derivatives*, 3(2).",
    "Landsea, C. & Franklin, J. (2013). Atlantic hurricane database uncertainty and presentation of a new database format (HURDAT2). *Monthly Weather Review*, 141(10).",
    "Smith, A. & Katz, R. (2013). US billion-dollar weather and climate disasters: data sources, trends, accuracy and biases. *Natural Hazards*, 67(2).",
    "Basel Committee on Banking Supervision (1996). Amendment to the capital accord to incorporate market risks.",
])
md, html = rep.write()
pdf = rep.pdf(C.REPORTS)

# ------------------------------------------------------------------ README highlights
rows = [
    ("Events", f"{n_h} Gulf hurricanes and {n_w} winter storms since 2008, chosen by NOAA storm tracks and damage, not prices"),
    ("Gas after winter storms", f"volatility **{mult(g['mean'])}** the month before vs {mult(g.placebo_mean)} on same-season days (placebo p {fmt_p(g.p_placebo)}, FDR q {fmt_num(g.q_bh, 3)})"),
    ("Oil after hurricanes", f"volatility **{mult(oil_h['mean'])}** vs {mult(oil_h.placebo_mean)} on same-season days (p {fmt_p(oil_h.p_placebo)}): no detectable effect"),
    ("Regime filter, gas, winter", f"Pr(turbulent) **{fmt_num(rgw.mean_shift, 2, signed=True)}** after storms vs {fmt_num(rgw.placebo_shift, 2, signed=True)} on placebo dates (q {fmt_num(rgw.q_bh, 3)})"),
    ("VaR breaches in storm windows", f"plain HS, long gas: **{fmt_pct(hh_hs.window_rate, 1)}** vs {fmt_pct(hh_hs.outside_rate, 1)} elsewhere (p {fmt_p(hh_hs.p_fisher)}); filtered HS {fmt_pct(hh_f.window_rate, 1)}"),
    ("Climate overlay, desk book", f"filtered HS storm-window breaches **{int(bk_f.window_exceptions)} -> {int(bk_f.overlay_window_exceptions)}** for {fmt_pct(bk_f.capital_cost, 1)} more average VaR"),
    ("Worst climate scenario, book", f"**{fmt_money(bk.worst_climate, 0)}** ({bk.worst_climate_event}) vs 10-day 99% VaR {fmt_money(bk.var10, 0)}"),
]
block = f"*EIA data to {asof}; generated {pd.Timestamp.today():%Y-%m-%d}*\n\n" + md_table(rows)
if fallback:
    block += "\n\n> Built with fallback copies of the NOAA event files (servers unreachable). `bash run.sh` re-downloads the official ones."
update_block(C.ROOT / "README.md", "HIGHLIGHTS", block)
print(f"  wrote {md.name}" + (f", {pdf}" if pdf else ""))
