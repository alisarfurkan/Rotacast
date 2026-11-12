"""WP3a phenology tests on synthetic MOD13Q1-like NDVI (no network)."""
import json

import numpy as np
import pandas as pd
import pytest

from rotacast.engine.phenology import analyze_ndvi


def _curve(doy, kind, amp=0.55):
    base = 0.17
    if kind == "winter":
        return base + amp * np.exp(-(((doy - 130) / 35) ** 2))
    if kind == "summer":
        return base + amp * np.exp(-(((doy - 210) / 35) ** 2))
    if kind == "double":
        return base + amp * np.exp(-(((doy - 110) / 25) ** 2)) + amp * np.exp(-(((doy - 245) / 25) ** 2))
    return base + 0.02 * np.sin(doy / 40)       # fallow


def make_ndvi(kinds: dict, seed=0, amps=None, bad=False):
    rng = np.random.default_rng(seed)
    rows = []
    for yr, kind in kinds.items():
        for k in range(23):
            doy = 1 + 16 * k
            v = float(_curve(doy, kind, (amps or {}).get(yr, 0.55)) + rng.normal(0, 0.008))
            rel = 0
            if bad and k % 7 == 3:        # cloudy composite: depressed value, reliability 3
                v, rel = 0.02, 3
            rows.append((pd.Timestamp(yr, 1, 1) + pd.Timedelta(days=doy - 1), v, rel))
    return pd.DataFrame(rows, columns=["date", "ndvi", "reliability"]).set_index("date")


@pytest.fixture(scope="module")
def result():
    kinds = {y: "winter" for y in range(2001, 2021)}
    kinds[2005] = "fallow"
    kinds[2010] = "summer"
    kinds[2013] = "double"
    return analyze_ndvi(make_ndvi(kinds, amps={2015: 0.25}, bad=True))   # 2015: weak winter crop


def test_json_and_keys(result):
    json.dumps(result)
    assert {"ndvi", "years", "bare_probability", "bare_windows", "stress_years"} <= set(result)
    assert set(result["years"][0]) >= {"year", "greenup_doy", "peak_doy", "peak_ndvi", "senescence_doy",
                                       "season_integral", "anomaly_z", "stress", "pattern"}
    assert len(result["bare_probability"]) == 23
    assert {"date", "ndvi", "ndvi_smooth"} == set(result["ndvi"][0])


def test_patterns(result):
    pat = {y["year"]: y["pattern"] for y in result["years"]}
    assert pat[2003] == "winter_crop" and pat[2018] == "winter_crop"
    assert pat[2005] == "fallow"
    assert pat[2010] == "summer_crop"
    assert pat[2013] == "double_crop"


def test_phenology_dates(result):
    by = {r["year"]: r for r in result["years"]}
    y = by[2003]
    assert 115 <= y["peak_doy"] <= 145 and y["peak_ndvi"] == pytest.approx(0.72, abs=0.06)
    assert 60 <= y["greenup_doy"] < y["peak_doy"] < y["senescence_doy"] <= 200
    assert by[2005]["greenup_doy"] is None


def test_bare_window_jul_oct(result):
    assert result["bare_windows"], "expected at least one bare window"
    w = max(result["bare_windows"], key=lambda w: w["end_doy"] - w["start_doy"])
    assert 175 <= w["start_doy"] <= 215 and 285 <= w["end_doy"] <= 365     # ~Jul .. Oct/Dec
    assert w["probability"] >= 0.8
    p = {b["doy"]: b["p_bare"] for b in result["bare_probability"]}
    assert p[241] > 0.8 and p[113] < 0.2           # late Aug bare, late Apr green


def test_stress_year(result):
    assert 2015 in result["stress_years"]
    assert 2005 not in result["stress_years"]      # fallow is deliberate, not stress
    z = {r["year"]: r["anomaly_z"] for r in result["years"]}
    assert z[2015] <= -1 < z[2003]


def test_unreliable_dropped():
    out = analyze_ndvi(make_ndvi({y: "winter" for y in range(2001, 2011)}, bad=True))
    raw = [r["ndvi"] for r in out["ndvi"] if r["ndvi"] is not None]
    assert min(raw) > 0.1                          # cloudy 0.02 values removed
    assert any(r["ndvi"] is None for r in out["ndvi"])
    assert min(r["ndvi_smooth"] for r in out["ndvi"]) > 0.1


def test_bare_threshold_parameter_and_never_bare():
    kinds = {y: "winter" for y in range(2001, 2011)}
    df = make_ndvi(kinds)
    df["ndvi"] += 0.3                              # perennial-like: never bare
    assert analyze_ndvi(df)["bare_windows"] == []
    out = analyze_ndvi(make_ndvi(kinds), bare_threshold=0.5)
    assert out["bare_threshold"] == 0.5 and len(out["bare_windows"]) >= 1
