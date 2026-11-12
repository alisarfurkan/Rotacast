"""WP3a climate tests: FAO-56 ET0 examples and climate_profile on synthetic data (no network)."""
import json

import numpy as np
import pandas as pd
import pytest

from rotacast.engine.climate import (add_et0, climate_profile, et0_penman_monteith,
                                     extraterrestrial_radiation, mann_kendall_p, sen_slope)


def test_et0_fao56_example18_brussels():
    df = pd.DataFrame(dict(tmax=[21.5], tmin=[12.3], rhmax=[84.0], rhmin=[63.0], wind2m=[2.078], rs=[22.07]),
                      index=pd.to_datetime(["2023-07-06"]))
    assert float(extraterrestrial_radiation(187, 50.8)) == pytest.approx(41.09, abs=0.1)  # FAO-56 Ex. 18: 41.09
    assert et0_penman_monteith(df, 50.8, 100).iloc[0] == pytest.approx(3.9, abs=0.1)
    d2 = df.drop(columns=["rhmax", "rhmin"]).assign(rh=(84 + 63) / 2)   # daily-mean RH path (eq. 19)
    assert et0_penman_monteith(d2, 50.8, 100).iloc[0] == pytest.approx(3.9, abs=0.3)


def test_et0_fao56_example17_bangkok_april():
    # FAO-56 Ex. 17: mean April conditions, ea = 2.85 kPa, u2 = 2.0 m/s, Rs ~ 22.65 MJ/m2/d, z = 2 m
    df = pd.DataFrame(dict(tmax=[34.8], tmin=[25.6], ea=[2.85], wind2m=[2.0], rs=[22.65]),
                      index=pd.to_datetime(["2023-04-15"]))
    assert et0_penman_monteith(df, 13.73, 2).iloc[0] == pytest.approx(5.7, abs=0.2)


def test_et0_nonnegative_and_add_et0():
    idx = pd.date_range("2020-01-01", periods=366)
    df = pd.DataFrame(dict(tmax=-5.0, tmin=-12.0, rh=90.0, wind2m=0.5, rs=1.0), index=idx)
    out = add_et0(df, 60.0, 50)
    assert "et0" not in df.columns and (out["et0"] >= 0).all()


def _synthetic(n_years=30, start=1991, trend=0.04, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{start}-01-01", f"{start + n_years - 1}-12-31")
    doy = idx.dayofyear.to_numpy()
    yrs = (idx.year - start).to_numpy()
    tmean = 12 - 13 * np.cos(2 * np.pi * (doy - 15) / 365.25) + trend * yrs + rng.normal(0, 2.5, len(idx))
    precip = np.where(rng.random(len(idx)) < 0.25, rng.gamma(1.2, 4.0, len(idx)), 0.0)
    df = pd.DataFrame(dict(tmax=tmean + 6, tmin=tmean - 6, tmean=tmean, precip=precip,
                           rh=55 + rng.normal(0, 5, len(idx)), wind2m=2.0 + rng.normal(0, .3, len(idx)),
                           rs=np.clip(10 + 9 * np.cos(2 * np.pi * (doy - 172) / 365.25), 3, 30)),
                      index=pd.DatetimeIndex(idx, name="date"))
    df.attrs.update(lat=37.6, lon=32.75, elevation_m=1010, source_id="nasa_power")
    return df


@pytest.fixture(scope="module")
def prof():
    return climate_profile(_synthetic(), 37.6)


def test_profile_structure_and_json(prof):
    json.dumps(prof)
    assert prof["period"] == [1991, 2020]
    assert len(prof["annual"]) == 30 and len(prof["monthly_normals"]) == 12
    assert set(prof["annual"][0]) == {"year", "precip_mm", "et0_mm", "tmean_c", "gdd0", "heat_days_35", "frost_days"}
    assert prof["shift"]["early"] == [1991, 2005] and prof["shift"]["late"] == [2006, 2020]
    assert {m["id"] for m in prof["shift"]["metrics"]} >= {
        "last_spring_frost", "first_fall_frost", "frost_free_days", "heat_days_35", "gdd0", "precip_mm",
        "et0_mm", "tmean_c", "spring_precip_mm", "summer_tmax_c"}
    assert prof["water_balance"]["annual_deficit_mm"] > 0 and prof["water_balance"]["aridity_index"] < 1


def test_warming_trend_detected(prof):
    m = {x["id"]: x for x in prof["shift"]["metrics"]}
    t = m["tmean_c"]
    assert t["trend_per_decade"] == pytest.approx(0.4, abs=0.25) and t["p_value"] < 0.05
    assert t["delta"] > 0.3
    assert m["gdd0"]["trend_per_decade"] > 0 and m["gdd0"]["p_value"] < 0.05
    assert m["last_spring_frost"]["delta"] < 0 and m["frost_free_days"]["delta"] > 0
    assert t["label"]["tr"] and t["label"]["en"]


def test_frost_dates_sensible(prof):
    f = prof["frost"]
    assert 40 < f["last_spring_doy"]["p50"] < 140
    assert 280 < f["first_fall_doy"]["p50"] < 365
    assert f["last_spring_doy"]["p10"] <= f["last_spring_doy"]["p50"] <= f["last_spring_doy"]["p90"]
    assert 150 < f["frost_free_days"]["p50"] < 300


def test_incomplete_years_excluded():
    df = _synthetic(n_years=12).iloc[100:-50]       # first and last year incomplete
    assert climate_profile(df, 37.6)["period"] == [1992, 2001]


def test_stat_helpers():
    x = np.arange(20.0)
    assert sen_slope(x, 2 * x + 1) == pytest.approx(2.0)
    assert mann_kendall_p(x) < 0.001
    assert mann_kendall_p(np.random.default_rng(0).normal(size=40)) > 0.05
