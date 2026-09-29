"""
01_data.py | Step 1: prices and the hazard catalogue.

Prices   EIA daily spot WTI, Brent, Henry Hub (FRED, falling back to a GitHub mirror), cleaned with
         regime_risk's data-quality rules, as log returns in %; plus the Brent-minus-WTI return.
Events   Gulf hurricanes from NOAA best tracks (NHC HURDAT2; dplyr's copy of it as fallback) and winter storms
         from NOAA NCEI's billion-dollar list (a bundled snapshot as fallback), mapped to trading days.
Outputs  tables/01_events.csv, 01_events_log.csv, 01_data_log.csv; data/processed/prices.pkl, events.pkl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

import config as C  # noqa: E402
from climrisk import events as ev  # noqa: E402
from climrisk.rr import data, fetch, version  # noqa: E402

for d in (C.TAB, C.FIG, C.DATA_RAW, C.DATA_PROC):
    d.mkdir(parents=True, exist_ok=True)
print(f"Step 1 | prices and events   [models: {version()}]")

# --- prices --------------------------------------------------------------------------------------
series, log = {}, []
for name, spec in C.DAILY.items():
    s, src = data.daily_series(name, spec, C.DATA_RAW)
    series[name] = s
    ok = s.dropna()
    log.append(dict(series=name, source=src, first=ok.index.min().date(), last=ok.index.max().date(), rows=len(ok)))
    print(f"  {name:9s} {len(ok):6d} rows to {ok.index.max().date()}  [{src}]")
prices = pd.DataFrame(series).loc[C.START_DATE:].dropna(how="all")
clean, rets, fixes, flags = data.clean_daily(prices, 6.0)
rets["Brent-WTI"] = rets["Brent"] - rets["WTI"]
pd.DataFrame(log).to_csv(C.TAB / "01_data_log.csv", index=False)
fixes.to_csv(C.TAB / "01_data_quality_fixes.csv", index=False)
print(f"  {len(rets)} common trading days, {rets.index[0].date()} to {rets.index[-1].date()}; {len(fixes)} cleaning actions logged")

# --- hurricanes: NOAA best tracks ----------------------------------------------------------------
elog = []
tracks, hsrc, htype = None, "", ""
try:
    idx, _ = fetch.fetch(C.HURDAT2_INDEX, C.DATA_RAW / "hurdat2_index.html", max_age_hours=24 * 7, timeout=30)
    newest = ev.newest_hurdat2(idx.read_text(errors="ignore"))
    urls = [C.HURDAT2_INDEX + newest] if newest else []
except Exception as e:
    print(f"  ! NHC file list unavailable ({str(e)[:70]})")
    urls = []
for url in dict.fromkeys(urls + [C.HURDAT2_KNOWN]):
    try:
        p, src = fetch.fetch(url, C.DATA_RAW / Path(url).name, max_age_hours=24 * 30, min_bytes=1_000_000, timeout=90)
        tracks, hsrc, htype = ev.parse_hurdat2(p.read_text()), src, "official"
        break
    except Exception as e:
        print(f"  ! {Path(url).name} unavailable ({str(e)[:70]})")
if tracks is None:
    p, src = fetch.fetch(C.HURDAT2_MIRROR, C.DATA_RAW / "dplyr_storms.csv", max_age_hours=24 * 30, min_bytes=100_000)
    tracks, hsrc, htype = ev.parse_dplyr_storms(p.read_text()), src, "fallback"
hur = ev.gulf_hurricanes(tracks, C.GULF_BOX, C.HURRICANE_KT, since=C.START_DATE)
last_track = tracks.time.max()
elog.append(dict(hazard="hurricane", source=hsrc, source_type=htype, data_through=last_track.date(), events=len(hur),
                 rule=f"status HU, >= {C.HURRICANE_KT} kt, lat {C.GULF_BOX['lat']}, lon {C.GULF_BOX['lon']}"))
print(f"  hurricanes: {len(hur)} since {C.START_DATE[:4]} (best track through {last_track.date()}, {htype})")

# --- winter storms: NOAA NCEI billion-dollar list ---------------------------------------------------
ncei, wsrc, wtype = None, "", ""
for url in C.NCEI_URLS:
    try:
        p, src = fetch.fetch(url, C.DATA_RAW / Path(url).name, max_age_hours=24 * 30, min_bytes=10_000, timeout=60)
        ncei, wsrc, wtype = ev.parse_ncei(p.read_text(errors="ignore")), src, "official"
        break
    except Exception as e:
        print(f"  ! {Path(url).name} unavailable ({str(e)[:70]})")
if ncei is None:
    snap = Path(ev.__file__).with_name("ncei_winter_snapshot.csv")
    ncei, wsrc, wtype = ev.parse_ncei(snap.read_text()), "bundled snapshot of NCEI events-US-1980-2024.csv", "fallback"
win = ev.winter_events(ncei, C.COLD_TYPES, C.COLD_MONTHS, C.MERGE_DAYS, since=C.START_DATE)
elog.append(dict(hazard="winter", source=wsrc, source_type=wtype, data_through=ncei.begin.max().date(), events=len(win),
                 rule=f"{' or '.join(C.COLD_TYPES)}, starting in months {C.COLD_MONTHS}, merged within {C.MERGE_DAYS} days"))
print(f"  winter storms: {len(win)} since {C.START_DATE[:4]} ({wtype})")

# --- align to trading days --------------------------------------------------------------------------
events = ev.align(pd.concat([hur, win], ignore_index=True).sort_values("date"), rets.index)
events["month"] = events["day0"].dt.month
events.to_csv(C.TAB / "01_events.csv", index=False, columns=["event", "short", "hazard", "date", "day0", "end", "detail"])
pd.DataFrame(elog).to_csv(C.TAB / "01_events_log.csv", index=False)
pd.to_pickle(dict(rets=rets, prices=clean, flags=flags), C.DATA_PROC / "prices.pkl")
pd.to_pickle(events, C.DATA_PROC / "events.pkl")
print(events[["short", "hazard", "date", "day0"]].to_string(index=False))

# --- figure: prices with every event marked ----------------------------------------------------------
import matplotlib.pyplot as plt  # noqa: E402

from climrisk.colors import HAZARD_COLOR, MODEL_COLOR, SERIES_COLOR  # noqa: E402,F401
from climrisk.rr import style  # noqa: E402

style.apply()
fig, axes = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True)
for ax, s, c in ((axes[0], "WTI", SERIES_COLOR["WTI"]), (axes[1], "HenryHub", SERIES_COLOR["HenryHub"])):
    ax.plot(clean.index, clean[s], color=c, lw=0.8)
    for e in events.itertuples():
        ax.axvline(e.day0, color=HAZARD_COLOR[e.hazard], lw=0.7, alpha=0.75)
    ax.set_yscale("log")
    ticks = [10, 20, 50, 100] if s == "WTI" else [2, 3, 5, 10, 20, 30]
    ax.set_yticks(ticks, [f"{t:g}" for t in ticks])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_ylabel("$/bbl" if s == "WTI" else "$/MMBtu")
    ax.set_title(C.LABELS[s], fontsize=10)
fig.suptitle(f"{(events.hazard == 'hurricane').sum()} Gulf hurricanes (pink) and {(events.hazard == 'winter').sum()} "
             "winter storms (purple), picked by physical rules", x=0.01, ha="left", fontweight="bold", fontsize=10.5)
fig.tight_layout()
style.save(fig, C.FIG / "01_events_timeline.png")
