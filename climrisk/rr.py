"""
rr.py | The models this project builds on, from github.com/n9omi/regime-risk-and-model-validation.

That repository's lib/ folder installs as the package `regime_risk` (setup.sh does it: from the folder next to
this one if it exists, otherwise from GitHub). If the package is not installed, this module loads it directly
from a copy in the sibling folder, so the scripts also run without setup.sh. Nothing is copied into this repo.

    from climrisk.rr import regimes, volatility, var_es      # Markov switching, GARCH-t / EWMA, VaR backtests
    from climrisk.rr import data, fetch                      # downloads with caching and fallbacks, cleaning rules
    from climrisk.rr import report, dashboard, style         # PDF report, HTML dashboard, chart style
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SIBLING = _ROOT.parent / "regime-risk-and-model-validation" / "lib"
INSTALL_HINT = ('pip install "regime-risk @ git+https://github.com/n9omi/regime-risk-and-model-validation.git"'
                " (or run bash setup.sh)")


def _load():
    try:
        return importlib.import_module("regime_risk"), "installed package"
    except ModuleNotFoundError:
        pass
    if (_SIBLING / "__init__.py").exists():
        spec = importlib.util.spec_from_file_location("regime_risk", _SIBLING / "__init__.py",
                                                      submodule_search_locations=[str(_SIBLING)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["regime_risk"] = mod
        spec.loader.exec_module(mod)
        return mod, f"folder {_SIBLING.parent.name}/lib"
    raise ModuleNotFoundError(f"The regime_risk models are not installed. {INSTALL_HINT}")


regime_risk, SOURCE = _load()

from regime_risk import (browser, dashboard, data, fetch, regimes, report, style, validation,  # noqa: E402,F401
                         var_es, volatility)


def version() -> str:
    try:
        from importlib.metadata import version as _v

        return f"regime-risk {_v('regime-risk')} ({SOURCE})"
    except Exception:
        return f"regime-risk ({SOURCE})"
