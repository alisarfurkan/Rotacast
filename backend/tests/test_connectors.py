"""WP1 connector tests: parsing of saved fixtures + offline cache behaviour. No network."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rotacast.connectors import cache, grace, modis, power, soil, terrain

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("ROTACAST_OFFLINE", raising=False)
    return tmp_path


def test_offline_cache_miss(tmp_cache, monkeypatch):
    monkeypatch.setenv("ROTACAST_OFFLINE", "1")
    with pytest.raises(cache.CacheMiss):
        cache.cached_get_json("x", "https://example.invalid/a", {"q": 1})
    with pytest.raises(cache.CacheMiss):
        cache.cached_get_bytes("x", "https://example.invalid/a")


def test_cache_hit_without_network(tmp_cache, monkeypatch):
    url, params = "https://example.invalid/a", {"q": 1}
    p = cache.cache_path("src", url, params)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"ok": True}))
    monkeypatch.setenv("ROTACAST_OFFLINE", "1")
    assert cache.cached_get_json("src", url, params) == {"ok": True}
    assert cache.request_key(url, {"b": 1, "a": 2}) == cache.request_key(url, {"a": 2, "b": 1})


def test_power_parse_fill_and_elevation():
    df, elev = power.parse_response(load("wp1_power_small.json"))
    assert elev == pytest.approx(1197.55)
    assert list(df.columns) == ["tmax", "tmin", "tmean", "precip", "rh", "wind2m", "rs", "gwetroot", "gwettop"]
    assert df.index.name == "date" and len(df) == 5
    assert math.isnan(df["tmax"].iloc[3]) and df["tmax"].iloc[0] == 5


def test_power_fetch_daily_from_cache(tmp_cache, monkeypatch):
    payload = load("wp1_power_small.json")
    from datetime import date
    start, end = date(2024, 1, 1), date(2024, 1, 5)
    (s, e), = power._chunks(start, end)
    params = {"parameters": ",".join(power.PARAM_MAP), "community": "AG", "longitude": 32.75,
              "latitude": 37.6, "start": "20240101", "end": "20240105", "format": "JSON"}
    p = cache.cache_path(power.SOURCE_ID, power.URL, params)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(payload))
    monkeypatch.setenv("ROTACAST_OFFLINE", "1")
    df = power.fetch_daily(37.6, 32.75, start, end)
    assert df.attrs["elevation_m"] == pytest.approx(1197.55) and df.attrs["source_id"] == "nasa_power"
    assert df.index.is_monotonic_increasing and df.index.freq is not None


def test_power_chunking_splits_long_ranges():
    from datetime import date
    ch = power._chunks(date(1991, 1, 1), date(2026, 11, 1))
    assert len(ch) == 4 and ch[0][0] == date(1991, 1, 1) and ch[-1][1] == date(2026, 11, 1)
    assert all(b[0] > a[1] for a, b in zip(ch, ch[1:]))


def test_modis_ndvi_frame():
    df = modis.build_ndvi_frame(load("wp1_modis_ndvi.json")["subset"], load("wp1_modis_rel.json")["subset"])
    assert df["ndvi"].iloc[0] == pytest.approx(0.4217)
    assert math.isnan(df["ndvi"].iloc[1])           # -3000 fill
    assert list(df["reliability"]) == [0, 3, 1]     # -1 fill -> 3
    assert df.index.name == "date"


def test_soilgrids_parse():
    sp = soil.parse_soilgrids(load("wp1_soilgrids_small.json"))
    assert sp.source_id == "soilgrids"
    assert sp.clay_pct == pytest.approx((5 * 32.6 + 10 * 32.6 + 15 * 35.0) / 30)
    assert sp.bulk_density == pytest.approx((5 * 1.37 + 10 * 1.42 + 15 * 1.46) / 30)
    assert 7.3 < sp.ph < 7.5
    assert sp.soc_gkg == pytest.approx((5 * 18 + 10 * 17 + 15 * 16) / 30)
    assert sp.texture_class == "silty clay loam"
    assert 0.1 < sp.wp < sp.fc < 0.5
    assert sp.taw_mm_per_m == pytest.approx((sp.fc - sp.wp) * 1000)


def test_texture_classes():
    assert soil.usda_texture_class(90, 5, 5) == "sand"
    assert soil.usda_texture_class(40, 40, 20) == "loam"
    assert soil.usda_texture_class(20, 20, 60) == "clay"
    assert soil.usda_texture_class(32, 35, 33) == "clay loam"
    assert soil.usda_texture_class(10, 70, 20) == "silt loam"


def test_saxton_rawls_loam_reference():
    fc, wp = soil.saxton_rawls_2006(40, 20, 12)  # loam, ~2 % OM
    assert 0.25 < fc < 0.33 and 0.10 < wp < 0.17


def test_soil_never_raises_offline(tmp_cache, monkeypatch):
    monkeypatch.setenv("ROTACAST_OFFLINE", "1")
    sp = soil.fetch_soil(37.6, 32.75)
    assert sp.source_id == "soil_default" and sp.texture_class == "clay loam"
    assert soil.fetch_soil(10.0, 10.0).source_id == "soil_default"


def test_terrarium_decode_and_slope():
    arr = terrain.decode_terrarium((FIX / "wp1_terrarium_ramp.png").read_bytes())
    assert arr.shape == (256, 256) and arr[0, 0] == pytest.approx(1000) and arr[0, 10] == pytest.approx(1030)
    win = arr[100:103, 50:53]
    # 3 m rise per pixel; with 30 m cells the slope is 10 %
    assert terrain.slope_from_window(win, 30.0) == pytest.approx(10.0)


def test_terrain_from_cache(tmp_cache, monkeypatch):
    png = (FIX / "wp1_terrarium_ramp.png").read_bytes()
    monkeypatch.setattr(terrain, "cached_get_bytes", lambda *a, **k: png)
    r = terrain.fetch_terrain(37.6, 32.75)
    assert r["source_id"] == "srtm_terrain_tiles" and r["slope_pct"] > 0


def test_grace_compute_series(tmp_path):
    xr = pytest.importorskip("xarray")
    lat = np.array([37.125, 37.375, 37.625, 37.875], dtype="float32")
    lon = np.array([32.125, 32.375], dtype="float32")
    data = np.stack([np.full((4, 2), 1.0), np.full((4, 2), 3.0)]).astype("float32")
    ds = xr.Dataset({"lwe_thickness": (("time", "lat", "lon"), data)},
                    coords={"time": [30.0, 60.0], "lat": lat, "lon": lon})
    nc = tmp_path / "g.nc"
    ds.to_netcdf(nc)
    s = grace.compute_bbox_series(nc, None, (32.0, 37.0, 33.0, 38.0))
    assert list(s.round(3)) == [1.0, 3.0]
    assert s.index[0] == pd.Timestamp("2002-01-01") and s.index[1] == pd.Timestamp("2002-03-01")


def test_grace_committed_csv_offline(monkeypatch):
    monkeypatch.setenv("ROTACAST_OFFLINE", "1")
    csv = grace._csv_path(grace.KONYA_BBOX)
    if not csv.exists():
        pytest.skip("konya_tws.csv not generated yet")
    s = grace.fetch_tws(grace.KONYA_BBOX)
    assert s.attrs["source_id"] == "grace_csr_mascon" and len(s) > 100
