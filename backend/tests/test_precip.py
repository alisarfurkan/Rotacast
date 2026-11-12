"""WP7: satellite precipitation connector parsing + POWER monthly bias correction (offline)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rotacast.connectors import precip

FIX = Path(__file__).parent / "fixtures"


def _synthetic(years=12, seed=1):
    idx = pd.date_range("2001-01-01", periods=365 * years, freq="D", name="date")
    rng = np.random.default_rng(seed)
    p = pd.Series(rng.gamma(0.4, 4.0, len(idx)) * (rng.random(len(idx)) < 0.4), index=idx)
    p[p < 0.01] = 0.0
    return p


def test_parse_fixture_marks_fill_as_nan():
    s = precip.parse_response(json.loads((FIX / "wp7_climateserv_imerg.json").read_text()))
    assert len(s) == 10 and s.index[0] == pd.Timestamp("2020-01-01")
    assert np.isnan(s.iloc[8]) and abs(s.iloc[5] - 17.55) < 1e-9


def test_correction_matches_monthly_totals_and_keeps_timing():
    p = _synthetic()
    mfac = pd.Series(p.index.month, index=p.index).map(lambda m: 0.5 + 0.02 * m)  # target / POWER ratio in (0.3, 1.5)
    sat = (p * mfac).rename("sat")
    sat.attrs["source_id"] = "gpm_imerg"
    df = pd.DataFrame({"precip": p, "tmax": 20.0})
    out = precip.bias_correct_power(df, sat)
    # long-term monthly totals now match the satellite
    for m in range(1, 13):
        assert abs(out.loc[out.index.month == m, "precip"].sum() - sat[sat.index.month == m].sum()) < 1e-6
    # timing preserved: rainy days stay rainy, order identical (monotone within a month)
    assert ((out["precip"] > 0) == (p > 0)).all()
    jan = p.index.month == 1
    assert np.corrcoef(out["precip"][jan], p[jan])[0, 1] > 0.999
    pc = out.attrs["precip_correction"]
    assert pc["source_id"] == "gpm_imerg" and pc["overlap_years"] >= 11
    assert abs(pc["factors_by_month"][3] - 0.56) < 0.01
    assert pc["sat_mean_mm"] < pc["power_mean_mm"]
    assert out["tmax"].equals(df["tmax"]) and df["precip"].equals(p)  # input untouched


def test_factors_clipped_and_applied_to_pre_overlap_years():
    p = _synthetic(years=12)
    sat = (p * 0.05).rename("sat")
    sat.attrs["source_id"] = "chirps"
    early = pd.Series(1.0, index=pd.date_range("1991-01-01", "2000-12-31", freq="D"))
    full = pd.concat([early, p])
    out = precip.bias_correct_power(pd.DataFrame({"precip": full}), sat)
    assert all(abs(v - 0.3) < 1e-9 for v in out.attrs["precip_correction"]["factors_by_month"].values())
    assert abs(out["precip"].iloc[0] - 0.3) < 1e-9  # 1991 corrected too


def test_short_overlap_raises():
    p = _synthetic(years=3)
    sat = p.copy()
    try:
        precip.bias_correct_power(pd.DataFrame({"precip": p}), sat)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
