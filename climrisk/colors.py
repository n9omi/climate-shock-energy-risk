"""colors.py | One colour per series and per hazard, used by every figure and the dashboard (never cycled)."""
from .rr import style

SERIES_COLOR = {"WTI": style.SERIES[0], "Brent": style.SERIES[1], "HenryHub": style.SERIES[2], "Brent-WTI": style.SERIES[3]}
HAZARD_COLOR = {"hurricane": style.SERIES[4], "winter": style.SERIES[6]}      # pink, purple: distinct from every series
MODEL_COLOR = {"Historical sim": style.SERIES[0], "Filtered HS": style.SERIES[2], "GARCH-t": style.SERIES[3]}
