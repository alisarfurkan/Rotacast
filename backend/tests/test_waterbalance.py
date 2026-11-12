"""WP3b: FAO-56 water balance tests (synthetic Konya-like weather, fake crops/soil, no network)."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pytest

from rotacast.engine import waterbalance as wb
from tests.fixtures.wp3b_fakes import make_crops, make_soil, make_weather


@pytest.fixture(scope="module")
def weather():
    return make_weather(1990, 2024)


@pytest.fixture(scope="module")
def soil():
    return make_soil()


@pytest.fixture(scope="module")
def crops():
    return make_crops()


def _closure_error(res, crop, soil) -> float:
    taw0 = soil.taw_mm_per_m * crop.fao56.root_depth_m[0]
    ds = (res.taw_end_mm - res.final_depletion_mm) - (taw0 - res.initial_depletion_mm)
    return abs(res.delta_storage_mm - ds)


@pytest.mark.parametrize("cid,irr,sow_year", [("wheat_winter", "none", 2000), ("maize_grain", "full", 2001),
                                             ("sugar_beet", "deficit", 2003), ("chickpea", "none", 2005),
                                             ("wheat_winter", "full", 1999)])
def test_mass_balance_closes(weather, soil, crops, cid, irr, sow_year):
    crop = crops[cid]
    sow = wb.find_sow_date(crop, weather, sow_year)
    res = wb.simulate_season(crop, sow, weather, soil, irr)
    # P_eff + I - ETa - DP (+ water entering with new root layers) = change in root-zone storage
    assert _closure_error(res, crop, soil) < 1.0
    assert res.drainage_mm >= 0 and res.eta_mm <= res.etc_mm + 1e-6
    assert res.effective_precip_mm <= res.precip_mm + 1e-9
    assert 0.0 <= res.yield_ratio <= 1.0


def test_mass_balance_constant_root_depth(weather, soil, crops):
    crop = deepcopy(crops["maize_grain"])
    crop.fao56.root_depth_m = (1.0, 1.0)     # no root growth -> plain P_eff + I - ETa - DP = -(Dr_end - Dr_0)
    res = wb.simulate_season(crop, wb.find_sow_date(crop, weather, 2002), weather, soil, "full")
    assert res.root_zone_gain_mm == 0
    lhs = res.effective_precip_mm + res.irrigation_mm - res.eta_mm - res.drainage_mm
    assert abs(lhs - (res.initial_depletion_mm - res.final_depletion_mm)) < 1.0


def test_full_irrigation_no_stress(weather, soil, crops):
    for year in (1995, 2000, 2007, 2012):
        crop = crops["maize_grain"]
        res = wb.simulate_season(crop, wb.find_sow_date(crop, weather, year), weather, soil, "full")
        assert res.stress_days == 0
        assert res.yield_ratio == pytest.approx(1.0, abs=1e-9)
        assert res.eta_mm == pytest.approx(res.etc_mm, rel=1e-6)
        assert res.irrigation_mm > 100


def test_rain_cut_more_stress_lower_yield(weather, soil, crops):
    dry = weather.copy()
    dry["precip"] = dry["precip"] * 0.2
    crop = crops["wheat_winter"]
    sow_w = wb.find_sow_date(crop, weather, 2003)
    sow_d = wb.find_sow_date(crop, dry, 2003)
    wet = wb.simulate_season(crop, sow_w, weather, soil, "none")
    low = wb.simulate_season(crop, sow_d, dry, soil, "none")
    assert low.stress_days > wet.stress_days
    assert low.yield_ratio < wet.yield_ratio
    assert low.eta_mm < wet.eta_mm


def test_irrigation_modes_ordering(weather, soil, crops):
    crop = crops["sugar_beet"]
    sow = wb.find_sow_date(crop, weather, 2004)
    none = wb.simulate_season(crop, sow, weather, soil, "none")
    deficit = wb.simulate_season(crop, sow, weather, soil, "deficit")
    full = wb.simulate_season(crop, sow, weather, soil, "full")
    assert none.irrigation_mm == 0
    assert full.irrigation_mm > deficit.irrigation_mm > 0
    assert none.yield_ratio <= deficit.yield_ratio <= full.yield_ratio + 1e-9


def test_sowing_rule_tmean_above_and_below(weather, crops):
    for year in (1995, 2005, 2015):
        d = wb.find_sow_date(crops["chickpea"], weather, year)
        a, b = crops["chickpea"].sowing.window_doy
        assert a <= d.timetuple().tm_yday <= b
        # first crossing: 7-day mean on that day >= threshold, day before (if inside the window) below
        roll = weather["tmean"].rolling(7, min_periods=1).mean()
        assert roll[str(d)] >= 7 or d.timetuple().tm_yday == b
        prev = d - timedelta(days=1)
        if d.timetuple().tm_yday > a:
            assert roll[str(prev)] < 7
        w = wb.find_sow_date(crops["wheat_winter"], weather, year)
        assert 270 <= w.timetuple().tm_yday <= 330
        assert w.month in (9, 10, 11)


def test_sowing_rule_window_end_when_never_crossing(weather, crops):
    cold = weather.copy()
    cold["tmean"] = -5.0
    d = wb.find_sow_date(crops["maize_grain"], cold, 2000)
    assert d == date(2000, 1, 1) + timedelta(days=140 - 1)       # window end
    assert wb.find_sow_date(crops["maize_grain"], weather, 2050) is None  # not covered


def test_sowing_rule_responds_to_warmer_weather(weather, crops):
    warm = weather.copy()
    warm["tmean"] = warm["tmean"] + 3.0
    for year in (1998, 2008):
        base = wb.find_sow_date(crops["maize_grain"], weather, year)
        w = wb.find_sow_date(crops["maize_grain"], warm, year)
        assert w <= base


def test_stage_scaling_capped(weather, soil, crops):
    crop = crops["maize_grain"]
    cold = weather.copy()
    cold["tmean"] = cold["tmean"] - 6.0       # slow GDD accumulation
    sow = date(2000, 5, 5)
    res = wb.simulate_season(crop, sow, cold, soil, "full")
    ref = sum(crop.fao56.stage_days)
    assert res.season_days <= round(ref * 1.3) + 4
    assert res.gdd_scale == pytest.approx(1.3)
    hot = weather.copy()
    hot["tmean"] = hot["tmean"] + 8.0
    res_h = wb.simulate_season(crop, sow, hot, soil, "full")
    assert res_h.season_days >= round(ref * 0.7) - 4
    assert res_h.gdd_scale == pytest.approx(0.7)


def test_coverage_error(weather, soil, crops):
    with pytest.raises(wb.WeatherCoverageError):
        wb.simulate_season(crops["sugar_beet"], date(2024, 9, 1), weather, soil)


def test_heat_frost_counted_in_sensitive_stage(weather, soil, crops):
    crop = deepcopy(crops["maize_grain"])
    hot = weather.copy()
    hot["tmax"] = 45.0
    res = wb.simulate_season(crop, date(2001, 5, 5), hot, soil, "full")
    stage_len = round(crop.fao56.stage_days[2] * res.gdd_scale)
    assert 0 < res.heat_days <= stage_len + 2
    assert res.frost_days == 0
    cold = weather.copy()
    cold["tmin"] = -10.0
    res2 = wb.simulate_season(crop, date(2001, 5, 5), cold, soil, "full")
    assert res2.frost_days > 0 and res2.heat_days == 0


def test_soil_cover_days_sensible(weather, soil, crops):
    crop = crops["maize_grain"]
    res = wb.simulate_season(crop, wb.find_sow_date(crop, weather, 2001), weather, soil, "full")
    assert 30 < res.soil_cover_days < res.season_days


def test_fallow_mass_balance_and_dry_summer(weather, soil):
    r = wb.simulate_fallow(date(2000, 7, 15), date(2000, 10, 20), weather, soil, 0.2)
    taw = soil.taw_mm_per_m * wb.BARE_BUCKET_M
    d0 = 0.2 * taw
    assert abs((r.effective_precip_mm - r.eta_mm - r.drainage_mm) - (d0 - r.final_depletion_mm)) < 1.0
    assert r.final_depletion_frac > 0.2           # dries out over the dry summer
    assert r.bare_days == 97 and r.erosive_bare_days == 19     # 1-19 October are erosive days
    wet = wb.simulate_fallow(date(2000, 11, 1), date(2001, 2, 1), weather, soil, 0.9)
    assert wet.final_depletion_frac < 0.9         # winter rain recharges


def test_end_date_truncates_season(weather, soil, crops):
    crop = crops["vetch_cover"]
    sow = wb.find_sow_date(crop, weather, 2000)
    full = wb.simulate_season(crop, sow, weather, soil)
    cut = wb.simulate_season(crop, sow, weather, soil, end_date=sow + timedelta(days=60))
    assert cut.season_days == 60 < full.season_days
    assert cut.harvest_date == sow + timedelta(days=60)
