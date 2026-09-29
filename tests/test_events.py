"""
test_events.py | The event rules, on small hand-made inputs with known answers (no internet needed).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C  # noqa: E402
from climrisk import events as ev  # noqa: E402

# Three storms in official HURDAT2 format:
#   INSIDE   hurricane (70-90 kt) inside the Gulf box          -> an event, day 0 = 2020-08-26
#   WEAK     tropical storm (50 kt) inside the box             -> not an event (below hurricane strength)
#   OUTSIDE  a 120 kt hurricane in the Atlantic east of Florida -> not an event (outside the box)
HURDAT = """AL132020,              INSIDE,      4,
20200825, 1800,  , TS, 24.9N,  88.0W,  60,  990,
20200826, 0600,  , HU, 26.1N,  90.5W,  70,  980,
20200826, 1800,  , HU, 28.0N,  92.5W,  90,  960,
20200827, 0600, L, HU, 29.8N,  93.3W, 130,  939,
AL142020,                WEAK,      2,
20200901, 0000,  , TS, 27.0N,  91.0W,  50,  995,
20200901, 1200,  , TS, 28.5N,  91.5W,  55,  993,
AL152020,             OUTSIDE,      2,
20200910, 0000,  , HU, 28.0N,  75.0W, 120,  940,
20200910, 1200,  , HU, 30.0N,  74.0W, 110,  945,
"""


def test_hurdat2_parser_reads_positions_and_winds():
    t = ev.parse_hurdat2(HURDAT)
    assert len(t) == 8 and set(t.name) == {"Inside", "Weak", "Outside"}
    row = t.iloc[1]
    assert (row.lat, row.lon, row.wind_kt, row.status) == (26.1, -90.5, 70, "HU")
    assert row.time == pd.Timestamp("2020-08-26 06:00")
    assert t.iloc[3].record == "L"


def test_gulf_box_rule_keeps_only_hurricanes_inside_the_box():
    e = ev.gulf_hurricanes(ev.parse_hurdat2(HURDAT), C.GULF_BOX, C.HURRICANE_KT)
    assert list(e.event) == ["Hurricane Inside (2020)"]
    assert e.date.iloc[0] == pd.Timestamp("2020-08-26")          # first fix in the box at >= 64 kt, not landfall
    assert "max 130 kt" in e.detail.iloc[0]


def test_dplyr_copy_gives_the_same_events_as_the_official_file():
    rows = ["name,year,month,day,hour,lat,long,status,category,wind,pressure,tropicalstorm_force_diameter,hurricane_force_diameter"]
    for line in HURDAT.splitlines():
        p = [x.strip() for x in line.split(",")]
        if p[0].startswith("AL"):
            name = p[1].title()
            continue
        status = {"HU": "hurricane", "TS": "tropical storm"}[p[3]]
        lat, lon = float(p[4][:-1]), -float(p[5][:-1])
        rows.append(f"{name},{p[0][:4]},{int(p[0][4:6])},{int(p[0][6:])},{int(p[1][:2])},{lat},{lon},{status},NA,{p[6]},{p[7]},NA,NA")
    a = ev.gulf_hurricanes(ev.parse_dplyr_storms("\n".join(rows)), C.GULF_BOX, C.HURRICANE_KT)
    b = ev.gulf_hurricanes(ev.parse_hurdat2(HURDAT), C.GULF_BOX, C.HURRICANE_KT)
    assert list(a.date) == list(b.date) and len(a) == 1


def test_newest_hurdat2_file_is_picked_from_the_nhc_listing():
    html = ('<a href="hurdat2-1851-2023-051124.txt">x</a> <a href="hurdat2-1851-2024-040425.txt">x</a> '
            '<a href="hurdat2-nepac-1949-2024-031725.txt">x</a> <a href="hurdat2-1851-2024-021525.txt">x</a>')
    assert ev.newest_hurdat2(html) == "hurdat2-1851-2024-040425.txt"
    assert ev.newest_hurdat2("nothing here") is None


NCEI = """Weather and Climate Billion-Dollar Disasters to affect the U.S. from 1980-2024
Cost values are in millions of dollars
Name,Disaster,Begin Date,End Date,CPI-Adjusted Cost,Unadjusted Cost,Deaths
"Winter Storm A (January 2024)",Winter Storm,20240112,20240114,1700,1690,20
"Cold Wave B (January 2024)",Winter Storm,20240114,20240118,1900,1910,41
"Spring Freeze (April 2007)",Freeze,20070404,20070410,2400,1400,0
"Southern Drought (2011)",Drought,20110101,20111231,15000,12000,95
"Winter Storm C (February 2021)",Winter Storm,20210210,20210219,27000,22686,262
"""


def test_winter_rule_filters_type_and_season_and_merges_close_episodes():
    w = ev.winter_events(ev.parse_ncei(NCEI), C.COLD_TYPES, C.COLD_MONTHS, C.MERGE_DAYS)
    assert len(w) == 2                                       # April freeze and drought dropped; A and B merged
    assert list(w.date) == [pd.Timestamp("2021-02-10"), pd.Timestamp("2024-01-12")]   # in date order
    merged = w.iloc[1]
    assert merged.end == pd.Timestamp("2024-01-18")
    assert "Winter Storm A" in merged.event and "Cold Wave B" in merged.event


def test_bundled_snapshot_parses():
    snap = Path(ev.__file__).with_name("ncei_winter_snapshot.csv")
    w = ev.winter_events(ev.parse_ncei(snap.read_text()), C.COLD_TYPES, C.COLD_MONTHS, C.MERGE_DAYS)
    assert len(w) >= 10 and (w.date.dt.month.isin(C.COLD_MONTHS)).all()


def test_day0_is_the_first_trading_day_on_or_after_the_event():
    days = pd.bdate_range("2021-02-01", "2021-02-28")        # weekdays only
    e = pd.DataFrame({"event": ["sat", "wed"], "hazard": "winter", "date": pd.to_datetime(["2021-02-13", "2021-02-10"])})
    a = ev.align(e, days)
    assert a.set_index("event").loc["sat", "day0"] == pd.Timestamp("2021-02-15")   # Saturday -> Monday
    assert a.set_index("event").loc["wed", "day0"] == pd.Timestamp("2021-02-10")
    early = pd.DataFrame({"event": ["before data"], "hazard": "winter", "date": pd.to_datetime(["2021-01-15"])})
    assert ev.align(early, days).empty                      # never snapped forward from before the data start


def test_window_mask_marks_exactly_the_risk_window():
    m = ev.window_mask([10], 30, (-2, 10))
    assert m.sum() == 13 and m[8] and m[20] and not m[7] and not m[21]
    assert ev.window_mask([1, 28], 30, (-2, 10)).sum() == 12 + 4          # clipped at both ends of the sample
