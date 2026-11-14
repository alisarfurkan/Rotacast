"""Water-only specialty crop model (cumin, fenugreek): FAO-56 balance with a fixed calendar, no network."""
from __future__ import annotations

import numpy as np
import pytest

from rotacast.engine import waterbalance as wb
from rotacast.engine.specialty_water import load_water_models, scale_stages, simulate_specialty_water
from tests.fixtures.wp3b_fakes import make_soil, make_weather

MODELS = load_water_models()


def test_models_load_with_sourced_parameters():
    cu, fe = MODELS["cumin"], MODELS["fenugreek"]
    assert cu.fao56.kc == (0.40, 1.00, 0.60) and fe.fao56.kc == (0.60, 1.00, 0.75)
    assert cu.fao56.root_depth_m == (0.10, 0.40) and fe.fao56.root_depth_m == (0.30, 0.80)
    assert cu.fao56.p == fe.fao56.p == 0.40
    assert (cu.sow_doy, cu.harvest_doy, fe.harvest_doy) == (57, 204, 214)
    assert sum(cu.fao56.stage_days) == cu.season_days == 147 and sum(fe.fao56.stage_days) == 157
    assert cu.practice == fe.practice == "rainfed"


def test_scale_stages_sums_exactly():
    assert sum(scale_stages([24, 40, 31, 19], 147)) == 147
    assert scale_stages([1, 1], 4) == (2, 2)


def test_etc_is_sum_of_kc_times_et0_and_irrigation_is_non_negative():
    wx = make_weather(1990, 2010)
    soil = make_soil()
    crop = MODELS["cumin"]
    years = list(range(1995, 2008))
    out = simulate_specialty_water(crop, wx, soil, years)
    # independent reconstruction of the Kc curve for one year
    p = wb.prepare_weather(wx)
    y = 2000
    i0 = wb._doy_idx(p, np.array([y]), crop.sow_doy)[0]
    l_ini, l_dev, l_mid, l_late = crop.fao56.stage_days
    kc_ini, kc_mid, kc_end = crop.fao56.kc
    kc = np.empty(sum(crop.fao56.stage_days))
    for t in range(len(kc)):
        if t < l_ini:
            kc[t] = kc_ini
        elif t < l_ini + l_dev:
            kc[t] = kc_ini + (kc_mid - kc_ini) * (t - l_ini + 1) / l_dev
        elif t < l_ini + l_dev + l_mid:
            kc[t] = kc_mid
        else:
            kc[t] = kc_mid + (kc_end - kc_mid) * (t - l_ini - l_dev - l_mid + 1) / l_late
    one = simulate_specialty_water(crop, wx, soil, [y])
    assert one["etc_mm"]["p50"] == pytest.approx(float((kc * p.et0[i0:i0 + len(kc)]).sum()), rel=1e-6)
    assert out["n_years"] == len(years)
    for k in ("etc_mm", "rainfed_eta_mm", "rain_eff_mm", "irr_need_full_m3_ha"):
        assert 0 <= out[k]["p10"] <= out[k]["p50"] <= out[k]["p90"], k
    assert out["rainfed_eta_mm"]["p50"] <= out["etc_mm"]["p50"] + 1e-9
    assert out["irr_need_full_m3_ha"]["p50"] > 0
    assert out["rainfed_irrigation_m3_ha"] == {"p10": 0.0, "p50": 0.0, "p90": 0.0}


def test_wetter_weather_needs_less_irrigation_and_uncovered_years_are_dropped():
    soil = make_soil()
    dry = simulate_specialty_water(MODELS["fenugreek"], make_weather(1990, 2010, rain_scale=0.5), soil, range(1995, 2008))
    wet = simulate_specialty_water(MODELS["fenugreek"], make_weather(1990, 2010, rain_scale=2.0), soil, range(1995, 2008))
    assert dry["irr_need_full_m3_ha"]["p50"] > wet["irr_need_full_m3_ha"]["p50"]
    assert dry["etc_mm"]["p50"] == pytest.approx(wet["etc_mm"]["p50"], rel=0.02)  # same ET0 series
    cut = simulate_specialty_water(MODELS["cumin"], make_weather(1990, 2010), soil, [1985, 2000, 2010, 2011])
    assert cut["years"] == [2000, 2010]  # 1985 is before the series, 2011 is after it
