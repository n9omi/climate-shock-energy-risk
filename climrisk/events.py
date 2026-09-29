"""
events.py | The hazard catalogue. Events are picked by a physical rule, never by what prices did.

    hurricane  NOAA best track (HURDAT2): a storm at >= 64 kt inside the northern Gulf box.
               Day 0 = the first date (UTC) it is inside the box at hurricane strength.
    winter     NOAA NCEI billion-dollar list: a "Winter Storm" or "Freeze" starting November to March.
               Day 0 = its begin date. Episodes starting within a week of each other are merged.

Both are mapped to trading days: day 0 is the first trading day on or after the event date.
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

HEADER = re.compile(r"^[A-Z]{2}\d{6}$")          # e.g. AL092017
STATUS_WORDS = {"hurricane": "HU", "tropical storm": "TS", "tropical depression": "TD", "extratropical": "EX",
                "subtropical storm": "SS", "subtropical depression": "SD", "other low": "LO",
                "tropical wave": "WV", "disturbance": "DB"}


# ---------------------------------------------------------------- hurricanes
def parse_hurdat2(text: str) -> pd.DataFrame:
    """
    Official HURDAT2 text: a header line per storm ("AL092017, HARVEY, 95,") followed by 6-hourly fixes
    ("20170825, 1800,  , HU, 27.8N,  96.8W, 115, ..."). Returns one row per fix.
    """
    rows, sid, name = [], None, None
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3 and HEADER.match(parts[0]):
            sid, name = parts[0], parts[1].title()
            continue
        if sid is None or len(parts) < 7 or not parts[0].isdigit():
            continue
        lat = float(parts[4][:-1]) * (1 if parts[4].endswith("N") else -1)
        lon = float(parts[5][:-1]) * (-1 if parts[5].endswith("W") else 1)
        rows.append((sid, name, parts[0] + parts[1].zfill(4), parts[2], parts[3], lat, lon, int(parts[6])))
    df = pd.DataFrame(rows, columns=["storm_id", "name", "time", "record", "status", "lat", "lon", "wind_kt"])
    df["time"] = pd.to_datetime(df["time"], format="%Y%m%d%H%M")
    return df


def parse_dplyr_storms(csv_text: str) -> pd.DataFrame:
    """The same best-track fixes as published in dplyr's `storms` table (HURDAT2, 1975 onward)."""
    s = pd.read_csv(io.StringIO(csv_text))
    df = pd.DataFrame({
        "storm_id": s["name"].astype(str) + "-" + s["year"].astype(str),
        "name": s["name"].astype(str),
        "time": pd.to_datetime(dict(year=s["year"], month=s["month"], day=s["day"], hour=s["hour"])),
        "record": "",
        "status": s["status"].map(STATUS_WORDS).fillna("LO"),
        "lat": s["lat"].astype(float), "lon": s["long"].astype(float), "wind_kt": s["wind"].astype(int),
    })
    return df


def gulf_hurricanes(tracks: pd.DataFrame, box: dict, min_kt: int = 64, since: str | None = None) -> pd.DataFrame:
    """One row per storm that is a hurricane (status HU, wind >= min_kt) inside the lat/lon box."""
    (la0, la1), (lo0, lo1) = box["lat"], box["lon"]
    t = tracks[(tracks.status == "HU") & (tracks.wind_kt >= min_kt)
               & tracks.lat.between(la0, la1) & tracks.lon.between(lo0, lo1)]
    if since:
        t = t[t.time >= pd.Timestamp(since)]
    if t.empty:
        return pd.DataFrame(columns=["event", "hazard", "date", "end", "detail"])
    g = t.groupby("storm_id").agg(name=("name", "first"), first=("time", "min"), last=("time", "max"),
                                  max_kt=("wind_kt", "max"), fixes=("time", "size")).reset_index()
    g = g.sort_values("first")
    return pd.DataFrame({
        "event": [f"Hurricane {n} ({f.year})" for n, f in zip(g.name, g["first"])],
        "short": [f"{n} {f.year}" for n, f in zip(g.name, g["first"])],
        "hazard": "hurricane",
        "date": g["first"].dt.normalize().values,
        "end": g["last"].dt.normalize().values,
        "detail": [f"max {k} kt in the Gulf box, {n} six-hourly fixes" for k, n in zip(g.max_kt, g.fixes)],
    }).reset_index(drop=True)


def newest_hurdat2(index_html: str) -> str | None:
    """Pick the newest Atlantic file name (hurdat2-1851-YYYY-MMDDYY.txt) from the NHC directory listing."""
    found = set(re.findall(r"hurdat2-1851-(\d{4})-(\d{6})\.txt", index_html))
    if not found:
        return None
    best = max(found, key=lambda m: (int(m[0]), m[1][4:6], m[1][0:4]))     # latest season, then release date
    return f"hurdat2-1851-{best[0]}-{best[1]}.txt"


# ---------------------------------------------------------------- winter storms
def parse_ncei(text: str) -> pd.DataFrame:
    """NCEI billion-dollar events CSV (title lines, then Name,Disaster,Begin Date,End Date,...)."""
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    start = next(i for i, ln in enumerate(lines) if ln.replace('"', "").startswith("Name,"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame({"name": df["Name"].astype(str).str.strip(), "disaster": df["Disaster"].astype(str).str.strip(),
                        "begin": pd.to_datetime(df["Begin Date"].astype(str).str[:8], format="%Y%m%d"),
                        "end": pd.to_datetime(df["End Date"].astype(str).str[:8], format="%Y%m%d")})
    return out


def winter_events(ncei: pd.DataFrame, types=("Winter Storm", "Freeze"), months=(11, 12, 1, 2, 3),
                  merge_days: int = 7, since: str | None = None) -> pd.DataFrame:
    e = ncei[ncei.disaster.isin(types) & ncei.begin.dt.month.isin(months)].sort_values("begin")
    if since:
        e = e[e.begin >= pd.Timestamp(since)]
    episodes = []
    for r in e.itertuples():
        if episodes and (r.begin - episodes[-1]["date"]).days <= merge_days:
            ep = episodes[-1]
            ep["end"] = max(ep["end"], r.end)
            ep["names"].append(r.name)
        else:
            episodes.append(dict(date=r.begin, end=r.end, names=[r.name], kind=r.disaster))
    return pd.DataFrame({
        "event": [" + ".join(ep["names"]) for ep in episodes],
        "short": [f"{'Freeze' if ep['kind'] == 'Freeze' else 'Winter storm'} {ep['date']:%b %Y}" for ep in episodes],
        "hazard": "winter",
        "date": [ep["date"] for ep in episodes],
        "end": [ep["end"] for ep in episodes],
        "detail": [f"NCEI billion-dollar event, {ep['date']:%b %d}-{ep['end']:%b %d %Y}" for ep in episodes],
    })


# ---------------------------------------------------------------- trading-day alignment
def align(events: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """Day 0 = first trading day on or after the event date. Adds `pos` (row in the price table) and `day0`."""
    e = events.copy()
    pos = trading_days.searchsorted(pd.to_datetime(e["date"]).values)
    e["pos"] = pos
    e = e[(e["pos"] < len(trading_days)) & (pd.to_datetime(e["date"]) >= trading_days[0])].copy()
    e["day0"] = trading_days[e["pos"].values]
    return e.reset_index(drop=True)


def window_mask(positions, n: int, win: tuple[int, int]) -> np.ndarray:
    """Boolean mask over n trading days: True inside [pos+win0, pos+win1] of any event."""
    m = np.zeros(n, bool)
    for p in np.asarray(positions, int):
        m[max(p + win[0], 0): min(p + win[1] + 1, n)] = True
    return m
