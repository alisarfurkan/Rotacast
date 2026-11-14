"""Konya zones: geometry helpers, MGM parser, runtime lookup and API guards (no network)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, box, mapping, shape

from rotacast.api.main import app
from rotacast.zones import build, definitions, lookup, mgm

MGM_SNIPPET = (
    "<html><body><p>Aydeniz İklim Sınıflandırması Kuraklık Katsayısı 1,61 İklim Tipi Çok Kurak "
    "Erinç İklim Sınıflandırması Yağış Etkinlik İndisi 15,41 İklim Tipi Yarı kurak "
    "DeMartonne İklim Sınıflandırması Kuraklık İndisi 7,86 İklim Tipi Yarı Kurak "
    "Trewartha İklim Sınıflandırması (evrensel sıcaklık ölçeğine göre) Kış mevsimi iklim tipi Kışları soğuk, (-0,19) "
    "Yaz mevsimi iklim tipi Yazları sıcak (23,34) Thornthwaite İklim Sınıflandırması İklim Sınıfı D,B'1,d,b'3 "
    "D : Yarı Kurak B'1 : 1. Derece Mezotermal İklim Sınıflandırmaları Hakkında Açıklama</p>"
    "<script>var x = 'Aydeniz';</script></body></html>"
).encode("utf-8")


def test_mgm_parse():
    d = mgm.parse(MGM_SNIPPET)
    assert d["aydeniz"] == {"index": 1.61, "type": "Çok Kurak"}
    assert d["erinc"]["index"] == pytest.approx(15.41)
    assert d["de_martonne"]["type"] == "Yarı Kurak"
    assert d["trewartha_winter"]["mean_temp_c"] == pytest.approx(-0.19)
    assert d["trewartha_summer"] == {"type": "Yazları sıcak", "mean_temp_c": 23.34}
    assert d["thornthwaite"]["class"] == "D,B'1,d,b'3"


def test_mgm_parse_rejects_changed_layout():
    with pytest.raises(ValueError):
        mgm.parse(b"<html>nothing here</html>")


def test_every_district_has_one_zone_and_ids_are_unique():
    m = definitions.district_zone_map()
    assert len(m) == 31
    ids = [z["id"] for z in definitions.ZONES]
    assert len(ids) == len(set(ids)) == 7
    assert all(z["stations"] for z in definitions.ZONES)
    assert all(code in mgm.STATIONS for z in definitions.ZONES for code in z["stations"])


def test_area_and_buffer_helpers():
    sq = box(32.0, 38.0, 33.0, 39.0)  # 1 x 1 degree at ~38.5 N
    assert build.area_km2(sq) == pytest.approx(111.32 ** 2 * np.cos(np.radians(38.5)), rel=1e-6)
    ring = build.buffer_km(Point(32.5, 38.5).buffer(1e-9), 10.0)
    assert build.area_km2(ring) == pytest.approx(np.pi * 100, rel=0.02)


def test_cells_and_grid():
    g = build.cells_to_geometry(np.array([32.005, 32.015]), np.array([38.005, 38.005]))
    assert g.bounds == pytest.approx((32.0, 38.0, 32.02, 38.01))
    lons, lats = build.grid_inside(box(32.0, 38.0, 32.05, 38.03))
    assert lons.size == 15


def test_fill_small_holes():
    outer = box(32.0, 38.0, 33.0, 39.0)
    poly = outer.difference(box(32.5, 38.5, 32.51, 38.51)).difference(box(32.1, 38.1, 32.4, 38.4))
    filled = build.fill_small_holes(poly, min_km2=25.0)
    assert len(filled.interiors) == 1  # the ~1 km2 hole is filled, the ~870 km2 one stays


@pytest.fixture()
def tiny_zones(tmp_path):
    prov = box(32.0, 37.0, 34.0, 39.0)
    lake = box(32.1, 37.1, 32.3, 37.3)
    west, east = box(32.0, 37.0, 33.0, 39.0).difference(lake), box(33.0, 37.0, 34.0, 39.0)
    fc = lambda feats: {"type": "FeatureCollection", "features": feats}  # noqa: E731
    props = lambda i, k: {"id": i, "key": k, "color": "#000", "name_tr": k, "name_en": k, "desc_tr": "", "desc_en": "",  # noqa: E731
                          "elevation_m": {"p10": 1000, "p50": 1100, "p90": 1400}, "stations": []}
    (tmp_path / "konya_boundary.geojson").write_text(json.dumps(fc([{"type": "Feature", "properties": {},
                                                                      "geometry": mapping(prov)}])))
    (tmp_path / "konya_lakes.geojson").write_text(json.dumps(fc([{"type": "Feature", "properties": {"name": "Göl"},
                                                                   "geometry": mapping(lake)}])))
    (tmp_path / "konya_zones.geojson").write_text(json.dumps(fc([
        {"type": "Feature", "properties": props(1, "west"), "geometry": mapping(west.buffer(-0.001))},
        {"type": "Feature", "properties": props(2, "east"), "geometry": mapping(east.buffer(-0.001))}])))
    return tmp_path


def test_lookup(tiny_zones):
    assert lookup.inside_konya(38.0, 32.5, tiny_zones)
    assert not lookup.inside_konya(40.0, 32.5, tiny_zones)
    assert lookup.zone_at(38.0, 32.5, tiny_zones)["key"] == "west"
    assert lookup.zone_at(38.0, 33.5, tiny_zones)["key"] == "east"
    assert lookup.zone_at(38.0, 33.0, tiny_zones)["key"] in {"west", "east"}  # gap -> nearest zone
    assert lookup.lake_at(37.2, 32.2, tiny_zones) == "Göl"
    assert lookup.zone_at(37.2, 32.2, tiny_zones) is None
    assert lookup.zone_at(40.0, 32.5, tiny_zones) is None


# --- against the committed data/zones files --------------------------------------------------------------------
client = TestClient(app)


def test_api_zones():
    r = client.get("/api/zones")
    assert r.status_code == 200
    body = r.json()
    feats = body["zones"]["features"]
    assert [f["properties"]["id"] for f in feats] == list(range(1, 8))
    assert sum(f["properties"]["area_km2"] for f in feats) == pytest.approx(40_000, rel=0.03)
    assert {f["properties"]["name"] for f in body["lakes"]["features"]} == {"Beyşehir Gölü", "Tuz Gölü", "Suğla Gölü"}
    assert all(shape(f["geometry"]).is_valid for f in feats)


@pytest.mark.parametrize("lat,lon,key", [(37.6, 32.75, "central"), (37.72, 33.55, "karapinar"), (36.99, 32.46, "toros"),
                                         (38.36, 31.42, "west"), (38.66, 32.92, "north"), (37.68, 31.75, "beysehir")])
def test_known_places(lat, lon, key):
    assert lookup.zone_at(lat, lon)["key"] == key


def test_analyze_rejects_outside_konya_and_lakes():
    r = client.post("/api/field/analyze", json={"lat": 39.93, "lon": 32.85})  # Ankara
    assert r.status_code == 422 and r.json()["detail"]["code"] == "outside_konya"
    r = client.post("/api/field/analyze", json={"lat": 37.75, "lon": 31.55})  # Beyşehir Gölü
    assert r.status_code == 422 and r.json()["detail"]["code"] == "on_lake"
