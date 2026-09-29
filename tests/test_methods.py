"""
test_methods.py | Known-answer tests for the event study, the placebo, the FDR correction and the VaR overlay,
plus a check that the regime_risk models load (the whole project depends on them).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from climrisk import eventstudy as es, overlay as ov, rr  # noqa: E402

EST, REL = (-250, -21), (-20, 30)


def _returns(n=3000, seed=0, scale=1.0):
    return np.random.default_rng(seed).standard_normal(n) * scale


def test_abnormal_returns_and_car_on_a_planted_jump():
    r = np.zeros(1200)
    r[600] = 5.0                                              # a 5% jump on day 0 of the event at 600
    ar, mu, sd = es.abnormal(r, np.array([600]), EST, REL)
    assert mu[0] == 0 and ar.shape == (1, REL[1] - REL[0] + 1)
    assert es.car(ar, REL[0], (0, 5))[0] == pytest.approx(5.0)
    assert es.car(ar, REL[0], (-5, -1))[0] == pytest.approx(0.0)


def test_abnormal_vol_is_log_of_the_ratio_to_the_month_before():
    r = np.ones(1000)
    r[500:511] = 2.0                                          # volatility doubles on days 0..+10
    assert es.abnormal_vol(r, np.array([500]))[0] == pytest.approx(np.log(2))


def test_placebo_detects_a_planted_effect_and_not_its_absence():
    dates = pd.bdate_range("2000-01-03", periods=4000)
    r = _returns(4000, seed=1)
    pos = np.arange(400, 3800, 200)                           # 17 events
    months = dates[pos].month
    pool = es.placebo_pool(dates, len(r), pos, 30, EST, REL)
    draws = es.placebo_draws(months, pool, 2000, seed=2)
    allpos = np.flatnonzero(es.valid_positions(np.arange(len(r)), len(r), EST, REL))
    av_all = np.full(len(r), np.nan)
    av_all[allpos] = es.abnormal_vol(r, allpos)
    null = es.placebo_p(float(es.abnormal_vol(r, pos).mean()), av_all[draws].mean(axis=1))
    r2 = r.copy()
    for p in pos:
        r2[p:p + 11] *= 3                                     # triple volatility after every event
    av2 = np.full(len(r), np.nan)
    av2[allpos] = es.abnormal_vol(r2, allpos)
    hit = es.placebo_p(float(es.abnormal_vol(r2, pos).mean()), av2[draws].mean(axis=1))
    assert hit < 0.01 < null


def test_placebo_dates_come_from_the_right_months_and_stay_away_from_events():
    dates = pd.bdate_range("2000-01-03", periods=3000)
    pos = np.array([800, 1500])
    pool = es.placebo_pool(dates, 3000, pos, 30, EST, REL)
    d = es.placebo_draws(dates[pos].month, pool, 500, seed=0)
    assert (dates[d[:, 0]].month == dates[800].month).all()
    assert np.min(np.abs(d[:, :, None] - pos[None, None, :])) > 30


def test_benjamini_hochberg_known_values():
    q = es.bh_qvalues([0.01, 0.04, 0.03, 0.50, np.nan])
    assert np.allclose(q[:4], [0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.50])
    assert np.isnan(q[4])


def test_sign_and_t_tests():
    share, p = es.sign_test([1, 2, 3, 4, 5, 6, 7, 8, 9, -1])
    assert share == 0.9 and p < 0.05
    t, pt = es.t_test(np.r_[_returns(50, 3) + 2.0])
    assert t > 5 and pt < 1e-6


def test_hs_var_matches_the_empirical_quantile():
    x = _returns(1500, 4)
    v = ov.var_hs(x, 1000, 500, 0.01)
    assert v[0] == pytest.approx(-np.sort(x[500:1000])[4])    # 5th worst of 500 = 1% quantile
    assert len(v) == 500


def test_overlay_uses_only_earlier_storms():
    x = np.ones(400) * 0.5
    var = np.ones(400) * ov.Z99                               # implies sd 1
    w = [np.arange(50, 63), np.arange(150, 163), np.arange(250, 263), np.arange(350, 363)]
    x[w[0]] = 2.0
    x[w[1]] = 2.0                                             # earlier storms moved 2 sd -> k = 2
    x[w[3]] = 50.0                                            # a huge later storm must not change earlier k
    k = ov.overlay_k(x, var, w, k_cap=3.0, min_past=2)
    assert k[0] == 1 and k[1] == 1                            # fewer than 2 past events
    assert k[2] == pytest.approx(2.0)
    x2 = x.copy()
    x2[w[3]] = 0.5
    assert ov.overlay_k(x2, var, w, 3.0, 2)[2] == k[2]        # no look-ahead
    x[w[2]] = 30.0
    assert ov.overlay_k(x, var, w, 3.0, 2)[3] == 3.0          # capped


def test_apply_overlay_scales_only_inside_windows():
    var = np.ones(100)
    out = ov.apply_overlay(var, [np.arange(10, 20)], np.array([1.5]))
    assert out[15] == 1.5 and out[5] == 1.0 and out[25] == 1.0


def test_regime_risk_models_load_and_work():
    assert "regime-risk" in rr.version()
    lr, p = rr.var_es.kupiec_pof(np.r_[np.zeros(990), np.ones(10)].astype(bool), 0.01)
    assert p > 0.9                                            # 10 breaches in 1,000 days at 1%: perfect coverage
    y, s = rr.regimes.simulate([0, 0], [0.5, 2.0], np.array([[0.98, 0.02], [0.05, 0.95]]), 3000, seed=5)
    res = rr.regimes.fit(y, K=2, seed=0)
    assert res.sigma[1] / res.sigma[0] == pytest.approx(4.0, rel=0.25)


@pytest.mark.skipif(not rr._SIBLING.exists(), reason="no regime-risk-and-model-validation folder next to this one")
def test_sibling_folder_fallback_loads_the_same_models(monkeypatch):
    import importlib

    real = importlib.import_module

    def no_package(name, *a, **k):
        if name == "regime_risk":
            raise ModuleNotFoundError(name)
        return real(name, *a, **k)

    saved = {k: v for k, v in sys.modules.items() if k == "regime_risk" or k.startswith("regime_risk.")}
    for k in saved:
        monkeypatch.delitem(sys.modules, k)
    monkeypatch.setattr(importlib, "import_module", no_package)
    mod, src = rr._load()
    assert src.startswith("folder") and hasattr(mod, "__path__")
    assert importlib.util.find_spec("regime_risk.var_es") is not None
