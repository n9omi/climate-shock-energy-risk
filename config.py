"""
config.py | Every assumption in one place. Change numbers here, never in the scripts.

The question: when a hurricane crosses the Gulf of Mexico or a winter storm freezes the country, what happens
to oil and gas prices, do standard risk models see it coming, and how much would a book lose?

Events are chosen by a physical rule (a storm's track, a disaster's damage), never by what prices did,
so the price response can be tested without circularity.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Read KEY=value lines from .env (never committed) into the environment, without overriding it."""
    import os

    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:
                os.environ.setdefault(k.strip(), v)


_load_dotenv(ROOT / ".env")     # e.g. FRED_API_KEY (optional)
DATA_RAW, DATA_PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
OUT = ROOT / "outputs"
TAB, FIG = OUT / "tables", OUT / "figures"
REPORTS, DOCS = ROOT / "reports", ROOT / "docs"
REPO_URL = "https://github.com/n9omi/climate-shock-energy-risk"
SEED = 7

# =============================================================================
# Prices: EIA daily spot benchmarks (the same sources as regime-risk-and-model-validation)
# =============================================================================
GH = "https://raw.githubusercontent.com/datasets"
DAILY = {
    "WTI":      dict(fred="DCOILWTICO",   mirror=f"{GH}/oil-prices/main/data/wti-daily.csv", label="WTI crude"),
    "Brent":    dict(fred="DCOILBRENTEU", mirror=f"{GH}/oil-prices/main/data/brent-daily.csv", label="Brent crude"),
    "HenryHub": dict(fred="DHHNGSP",      mirror=f"{GH}/natural-gas/main/data/daily.csv", label="Henry Hub gas"),
}
START_DATE = "2007-01-02"        # full daily coverage for all three series from here (the mirror is patchy before)
# Series studied: the three benchmarks plus the Brent-minus-WTI return (a long-Brent, short-WTI spread position),
# which isolates US Gulf Coast disruptions from the global oil price.
SERIES = ["WTI", "Brent", "HenryHub", "Brent-WTI"]
LABELS = {"WTI": "WTI crude", "Brent": "Brent crude", "HenryHub": "Henry Hub gas", "Brent-WTI": "Brent - WTI spread"}

# =============================================================================
# Hazard catalogue
# =============================================================================
# Hurricanes: NOAA NHC best-track data (HURDAT2, 6-hourly positions and winds). A storm is an event if it is
# at hurricane strength (>= 64 kt) while inside the northern Gulf box below: the federal offshore oil and gas
# production area and the Texas-to-Alabama refining coast. Day 0 = the first date it is in the box as a hurricane.
HURDAT2_INDEX = "https://www.nhc.noaa.gov/data/hurdat/"                        # newest file is picked from here
HURDAT2_KNOWN = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2024-040425.txt"
HURDAT2_MIRROR = "https://raw.githubusercontent.com/tidyverse/dplyr/main/data-raw/storms.csv"  # HURDAT2 1975-2024, via dplyr
GULF_BOX = dict(lat=(25.5, 30.5), lon=(-98.0, -86.0))
HURRICANE_KT = 64

# Winter storms: NOAA NCEI Billion-Dollar Weather and Climate Disasters, events typed "Winter Storm" or "Freeze"
# that begin between November and March. Selected by damage (>= $1 billion), not by gas prices. Episodes that
# start within MERGE_DAYS of each other are merged. NOAA stopped updating this database in 2025, so it ends in 2024.
NCEI_URLS = ["https://www.ncei.noaa.gov/access/billions/events-US-1980-2024.csv",
             "https://www.nodc.noaa.gov/archive/arc0153/0209268/16.16/data/0-data/events-US-1980-2023.csv"]
COLD_TYPES = ("Winter Storm", "Freeze")
COLD_MONTHS = (11, 12, 1, 2, 3)
MERGE_DAYS = 7
HAZARDS = {"hurricane": "Gulf hurricane", "winter": "Winter storm / freeze"}
HAZ_PLURAL = {"hurricane": "Gulf hurricanes", "winter": "Winter storms and freezes"}

# =============================================================================
# Event study (MacKinlay, 1997), in trading days relative to day 0
# =============================================================================
EST_WIN = (-250, -21)            # estimation window for the normal return and normal volatility
WINDOWS = {"Run-up [-5,-1]": (-5, -1), "Impact [0,+5]": (0, 5), "Full [-5,+10]": (-5, 10)}
MAIN_WINDOW = "Full [-5,+10]"
VOL_WIN = (0, 10)                # abnormal volatility: realised vol in [0,+10] ...
VOL_BASE = (-30, -11)            # ... relative to the month just before (ends before any storm forecast)
PATH_WIN = (-20, 30)             # for the average-path charts
N_PLACEBO = 5000                 # month-matched placebo draws
PLACEBO_BUFFER = 30              # placebo days must be this many trading days away from any real event

# =============================================================================
# Regimes: 2-state Markov switching from regime_risk, fitted once on the training years, then run as a
# real-time filter (no look-ahead); only events after the training period are scored
# =============================================================================
REGIME_TRAIN_END = "2014-12-31"
REGIME_WIN = {"before": (-15, -6), "after": (1, 10)}

# =============================================================================
# Value-at-Risk and the climate overlay
# =============================================================================
BOOK = {"WTI": 4_000_000, "Brent": -2_000_000, "HenryHub": 2_000_000}   # the same desk book as regime-risk
POSITIONS = {"Book": BOOK, "Long WTI $1mm": {"WTI": 1_000_000}, "Long Henry Hub $1mm": {"HenryHub": 1_000_000}}
VAR_P = 0.01                     # 99% one-day VaR
HS_WINDOW = 500
EWMA_LAMBDA = 0.94
GARCH_REFIT_DAYS = 250           # GARCH-t re-estimated once a year on all data to date
BACKTEST_START = "2010-01-04"
RISK_WIN = (-2, 10)              # days treated as "inside a storm": from two trading days before day 0 (NHC
                                 # hurricane watches and NWS winter storm watches give about that much warning)
K_CAP = 3.0                      # the overlay never more than triples VaR
MIN_PAST_EVENTS = 2              # the overlay switches on once this many past events of the hazard exist
STRESS_WIN = (-2, 10)            # historical scenario horizon for the stress tests
