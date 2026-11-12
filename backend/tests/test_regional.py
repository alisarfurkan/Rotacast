"""Basin View aggregation tests (no network)."""
import json
import math

import numpy as np

from rotacast import regional as R


def _cell(irr_ha, base_w, strat_w, base_t, strat_t, trend_extra=0.0):
    def hz(w, t):
        return {"water_m3_ha": w, "crop_t_ha_yr": t}
    now = {"baseline": hz(base_w, base_t), "water_saver": hz(strat_w, strat_t)}
    trend = {"baseline": hz(base_w, base_t),
             "water_saver": hz({k: v + trend_extra for k, v in strat_w.items()}, strat_t)}
    return {"irrigated_ha": irr_ha, "strategies": {
        a: {"horizons": {"now": now[a]["water_m3_ha"] and now[a], "trend": trend[a]}} for a in now}}


def _params():
    return R.BasinParams(adoption_rates=(0.1, 0.5), horizons=(5, 10))


def test_power_cells_cover_bbox():
    cells = R.power_cells()
    assert 20 <= len(cells) <= 40
    assert all(abs((c["lat"] / 0.5) - round(c["lat"] / 0.5)) < 1e-9 for c in cells)
    total = sum(c["area_km2"] for c in R.power_cells(min_overlap_frac=0.0))
    assert math.isclose(total, R.rect_area_km2(37.0, 38.8, 32.0, 34.5), rel_tol=1e-6)


def test_aggregate_two_cells():
    bw = {"p10": 4000.0, "p50": 5000.0, "p90": 6000.0}
    sw1 = {"p10": 1000.0, "p50": 2000.0, "p90": 3000.0}
    sw2 = {"p10": 3000.0, "p50": 4000.0, "p90": 5000.0}
    c1 = _cell(10_000, bw, sw1, {"wheat": 2.0, "maize": 4.0}, {"wheat": 3.0, "lentil": 1.0})
    c2 = _cell(30_000, bw, sw2, {"wheat": 2.0, "maize": 4.0}, {"wheat": 3.0, "lentil": 1.0}, trend_extra=500.0)
    agg = R.aggregate([c1, c2], _params(), grace_loss_mm3=1000.0)
    assert agg["baseline"]["irrigated_ha"] == 40_000
    assert math.isclose(agg["baseline"]["irrigation_demand_mm3_yr"]["p50"], 40_000 * 5000 / 1e6)
    h5 = agg["scenarios"]["water_saver"]["0.5"]["5"]
    # p50 change: 0.5 * (10000*(2000-5000) + 30000*(4000-5000)) / 1e6 = -30 Mm3
    assert math.isclose(h5["irrigation_change_mm3_yr"]["p50"], -30.0)
    assert math.isclose(h5["grace_offset_pct"]["p50"], 3.0)
    assert h5["irrigation_change_mm3_yr"]["p10"] <= h5["irrigation_change_mm3_yr"]["p50"] <= h5["irrigation_change_mm3_yr"]["p90"]
    prod = {x["crop_id"]: x["change_t_yr"] for x in h5["production_change_t_yr"]}
    assert math.isclose(prod["wheat"], 0.5 * 40_000 * 1.0)
    assert math.isclose(prod["maize"], -0.5 * 40_000 * 4.0)
    assert math.isclose(prod["lentil"], 0.5 * 40_000 * 1.0)
    # trend horizon: cell 2 uses +500 m3/ha -> change p50 = 0.5*(10000*-3000 + 30000*-500)/1e6 = -22.5
    h10 = agg["scenarios"]["water_saver"]["0.5"]["10"]
    assert h10["climate"] == "trend_continuation"
    assert math.isclose(h10["irrigation_change_mm3_yr"]["p50"], -22.5)
    # adoption scales linearly
    h5_10 = agg["scenarios"]["water_saver"]["0.1"]["5"]
    assert math.isclose(h5_10["irrigation_change_mm3_yr"]["p50"], -6.0)


def test_aggregate_without_grace_gives_null():
    bw = {"p10": 1.0, "p50": 2.0, "p90": 3.0}
    c = _cell(1000, bw, bw, {"wheat": 1.0}, {"wheat": 1.0})
    agg = R.aggregate([c], _params(), grace_loss_mm3=None)
    assert agg["scenarios"]["water_saver"]["0.1"]["5"]["grace_offset_pct"] is None


def test_json_roundtrip_strict():
    bw = {"p10": 1.0, "p50": 2.0, "p90": float("nan")}
    c = _cell(1000, bw, bw, {"wheat": np.float64(1.0)}, {"wheat": 1.0})
    agg = R.aggregate([c], _params())
    s = json.dumps(R.clean({"x": agg, "n": np.int64(3), "bad": float("inf")}), allow_nan=False)
    back = json.loads(s)
    assert back["bad"] is None and back["n"] == 3
    assert back["x"]["baseline"]["irrigated_ha"] == 1000


def test_grace_summary_degrades(monkeypatch):
    def boom(_bbox):
        raise RuntimeError("offline")
    monkeypatch.setattr(R.grace_mod, "fetch_tws", boom)
    g = R.grace_summary()
    assert g["available"] is False and g["trend_cm_yr"] is None and g["area_km2"] > 10_000
    json.dumps(R.clean(g), allow_nan=False)


def test_grace_summary_trend(monkeypatch):
    import pandas as pd
    idx = pd.date_range("2003-01-01", periods=240, freq="MS")
    y = -1.0 * (idx.year + (idx.month - 0.5) / 12 - 2003) + np.random.default_rng(1).normal(0, 0.5, 240)
    s = pd.Series(y, index=idx)
    monkeypatch.setattr(R.grace_mod, "fetch_tws", lambda b: s)
    g = R.grace_summary()
    assert abs(g["trend_cm_yr"] + 1.0) < 0.1
    assert g["volume_change_mm3_yr"] < 0
    lo, hi = g["trend_ci95_cm_yr"]
    assert lo < g["trend_cm_yr"] < hi
    # 1 cm/yr over ~44,000 km2 = 440 Mm3/yr
    assert math.isclose(g["volume_change_mm3_yr"] / g["trend_cm_yr"], g["area_km2"] / 100.0, rel_tol=1e-9)
