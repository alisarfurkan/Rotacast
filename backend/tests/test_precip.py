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


# ---- coverage / retry (no network: _fetch_chunk is mocked) ----
from datetime import date  # noqa: E402

import pytest  # noqa: E402


def _chunk(s, e):
    return pd.Series(1.0, index=pd.date_range(s, e, freq="D", name="date"), name="precip")


def _patch(monkeypatch, fail):
    """fail(source_id, year, attempt_no) -> True to raise. Returns the attempts counter."""
    attempts = {}

    def fake(source_id, lat, lon, s, e):
        key = (source_id, s.year)
        attempts[key] = attempts.get(key, 0) + 1
        if fail(source_id, s.year, attempts[key]):
            raise RuntimeError("boom")
        return _chunk(s, e)

    monkeypatch.setattr(precip, "_fetch_chunk", fake)
    monkeypatch.setattr(precip, "is_offline", lambda: False)
    return attempts


def test_retry_pass_recovers_failed_years_full_coverage(monkeypatch):
    _patch(monkeypatch, lambda sid, y, n: y in (2004, 2007) and n == 1)  # first attempt fails, retry works
    ser = precip.fetch_precip_daily(37.6, 32.75, date(2001, 1, 1), date(2012, 12, 31))
    assert ser.attrs["coverage"] == {"requested_years": 12, "obtained_years": 12, "missing_years": []}
    assert ser.attrs["source_id"] == "chirps"
    assert {2004, 2007} <= set(ser.index.year)


def test_persistent_failure_rejects_source_and_falls_back(monkeypatch):
    # chirps loses 4/12 years for good (coverage 0.67 < 0.8); imerg is complete -> next source wins
    _patch(monkeypatch, lambda sid, y, n: sid == "chirps" and y in (2003, 2004, 2005, 2006))
    ser = precip.fetch_precip_daily(37.6, 32.75, date(2001, 1, 1), date(2012, 12, 31))
    assert ser.attrs["source_id"] == "gpm_imerg"
    assert ser.attrs["coverage"]["missing_years"] == []


def test_all_sources_below_min_coverage_raises(monkeypatch):
    _patch(monkeypatch, lambda sid, y, n: y in (2003, 2004, 2005, 2006))
    with pytest.raises(RuntimeError, match="coverage too low"):
        precip.fetch_precip_daily(37.6, 32.75, date(2001, 1, 1), date(2012, 12, 31))


def test_small_gap_accepted_and_reported(monkeypatch):
    _patch(monkeypatch, lambda sid, y, n: y == 2009)  # 1/12 missing = 0.917 coverage, still accepted
    ser = precip.fetch_precip_daily(37.6, 32.75, date(2001, 1, 1), date(2012, 12, 31))
    assert ser.attrs["coverage"] == {"requested_years": 12, "obtained_years": 11, "missing_years": [2009]}


def test_retry_pass_stops_after_two_consecutive_failures(monkeypatch):
    attempts = _patch(monkeypatch, lambda sid, y, n: sid == "chirps" and y in (2002, 2003, 2004, 2005))
    precip._fetch_source("chirps", 37.6, 32.75, date(2001, 1, 1), date(2012, 12, 31))
    # 4 failed years: retry pass tries 2002, 2003 (two consecutive failures) then stops before 2004/2005
    assert attempts[("chirps", 2002)] == 2 and attempts[("chirps", 2003)] == 2


def test_no_retry_when_offline(monkeypatch):
    attempts = _patch(monkeypatch, lambda sid, y, n: y == 2005)
    monkeypatch.setattr(precip, "is_offline", lambda: True)
    ser = precip._fetch_source("chirps", 37.6, 32.75, date(2001, 1, 1), date(2012, 12, 31))
    assert attempts[("chirps", 2005)] == 1
    assert ser.attrs["coverage"]["missing_years"] == [2005]


def test_coverage_copied_into_precip_correction():
    p = _synthetic()
    sat = (p * 0.8).rename("sat")
    sat.attrs.update({"source_id": "chirps", "coverage": {"requested_years": 12, "obtained_years": 12, "missing_years": []}})
    out = precip.bias_correct_power(pd.DataFrame({"precip": p}), sat)
    assert out.attrs["precip_correction"]["coverage"] == sat.attrs["coverage"]
    sat.attrs.pop("coverage")
    assert "coverage" not in precip.bias_correct_power(pd.DataFrame({"precip": p}), sat).attrs["precip_correction"]
