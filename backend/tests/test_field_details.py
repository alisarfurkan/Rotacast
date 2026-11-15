"""Optional field inputs (CONTRACTS section 6): polygon, soil override, excluded crops, irrigation method, water quota,
declared yields, crop history, applied irrigation. Offline (cached Cumra data), no network."""
import json
import math
import os
from pathlib import Path

import pytest

os.environ["ROTACAST_OFFLINE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from rotacast import geometry  # noqa: E402
from rotacast.api.main import AnalyzeRequest, app  # noqa: E402
from rotacast.engine.rotations import IRRIGATION_EFFICIENCY  # noqa: E402
from rotacast.field_inputs import normalize_polygon  # noqa: E402
from rotacast.knowledge.crops import load_crops  # noqa: E402
from rotacast.report import (TEXTURE_CLAY_SAND, build_field_report, get_field_report, normalize_request,  # noqa: E402
                             override_soil)
from rotacast.connectors import soil as soil_mod  # noqa: E402

REQ = {"lat": 37.60, "lon": 32.75}
FIXTURE = Path(__file__).parent / "fixtures" / "konya_default_strategies.json"
# Fixture = output of `main` (zone cards) for the default Konya request, so field_details-free requests must match it.
SNAP_KEYS = ("id", "archetype", "steps", "indicators", "score", "score_breakdown", "parts", "coverage", "water_coverage", "trials")
client = TestClient(app)


def _rect(lon0, lat0, dlon, dlat):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon0 + dlon, lat0], [lon0 + dlon, lat0 + dlat],
                                                  [lon0, lat0 + dlat], [lon0, lat0]]]}


def _p50(b):
    return b["p50"] if isinstance(b, dict) else b


def _close(a, b, path="") -> None:
    if isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys(), path
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-12), path
    else:
        assert a == b, path


def _keeps_current(s) -> bool:
    """Zone card whose field part is the user's own current rotation (the 'innovative' card): by design it is not
    filtered by excluded crops or the quota, and it inherits the current rotation's water use."""
    return any(p.get("role") == "current_rotation" for p in s.get("parts", []))


def _fact_ids_ok(rep):
    ids = {f["id"] for f in rep["facts"]}
    assert len(ids) == len(rep["facts"])
    for s in rep["strategies"]:
        for sec in ("why", "benefits", "risks"):
            for e in s["evidence"][sec]:
                assert set(e.get("facts", [])) <= ids
    assert {f["source_id"] for f in rep["facts"]} <= {x["id"] for x in rep["sources"]}


@pytest.fixture(scope="module")
def default():
    return build_field_report(REQ)


# ---------------------------------------------------------------- regression (default request unchanged)
def test_default_strategies_match_snapshot(default):
    snap = json.loads(FIXTURE.read_text(encoding="utf-8"))
    got = [{k: s[k] for k in SNAP_KEYS if k in s} for s in default["strategies"]]
    _close(got, snap)


def test_empty_and_null_details_equal_default(default):
    for extra in ({"field_details": {}}, {"field_details": None}, {"field_polygon": None, "field_details": {"excluded_crops": [],
                                                                                                         "yields_t_ha": {}}}):
        assert build_field_report({**REQ, **extra}) == default
    for k in ("user_inputs", "irrigation", "quota", "yield_check", "history_check", "irrigation_check"):
        assert k not in default
    assert "area_ha" not in default["location"] and "polygon" not in default["location"]
    assert all("exceeds_quota" not in s for s in default["strategies"])


def test_api_none_fields_normalize_like_default():
    dumped = AnalyzeRequest().model_dump()
    assert dumped["field_polygon"] is None and dumped["field_details"] is None
    n = normalize_request(dumped)
    assert "polygon" not in n and "details" not in n
    assert n == normalize_request({})


def test_cache_key_includes_new_inputs():
    a = normalize_request({**REQ, "field_details": {"irrigation_method": "drip"}})
    b = normalize_request({**REQ, "field_details": {"irrigation_method": "flood"}})
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------- polygon
def test_polygon_area_and_centroid_rectangle():
    d = 0.01
    poly = _rect(32.70, 37.60, d, d)
    n = normalize_polygon(poly)
    r = geometry.EARTH_RADIUS_M
    lat_a, lat_b = math.radians(37.60), math.radians(37.61)
    expected_ha = (math.radians(d) * r ** 2 * (math.sin(lat_b) - math.sin(lat_a))) / 1e4  # exact sphere band area
    assert n["area_ha"] == pytest.approx(expected_ha, rel=0.01)
    assert 90 < n["area_ha"] < 110
    assert n["centroid"][0] == pytest.approx(32.705, abs=1e-9)
    assert n["centroid"][1] == pytest.approx(37.605, abs=1e-9)
    assert n["ring"][0] == n["ring"][-1] and len(n["ring"]) == 5


def test_open_ring_accepted():
    poly = _rect(32.70, 37.60, 0.002, 0.002)
    poly["coordinates"][0].pop()
    assert len(normalize_polygon(poly)["ring"]) == 5


def test_polygon_422s():
    bowtie = {"type": "Polygon", "coordinates": [[[32.70, 37.60], [32.71, 37.61], [32.71, 37.60], [32.70, 37.61], [32.70, 37.60]]]}
    two = {"type": "Polygon", "coordinates": [[[32.70, 37.60], [32.71, 37.61], [32.70, 37.60]]]}
    for poly in (bowtie, two, _rect(32.0, 37.0, 1.0, 1.0), _rect(32.70, 37.60, 1e-5, 1e-5)):
        r = client.post("/api/field/analyze", json={"field_polygon": poly})
        assert r.status_code == 422, poly
        assert r.json()["detail"][0]["loc"][:2] == ["body", "field_polygon"]
    r = client.post("/api/field/analyze", json={"field_polygon": bowtie})
    assert r.json()["detail"][0]["loc"] == ["body", "field_polygon", "coordinates"]
    assert "self-intersect" in r.json()["detail"][0]["msg"]


# ---------------------------------------------------------------- 422 validation of field_details
@pytest.mark.parametrize("details,loc_tail", [
    ({"water_quota_m3_yr": -5}, ["water_quota_m3_yr"]),
    ({"soil": {"clay_pct": 70, "sand_pct": 40}}, ["soil"]),
    ({"soil": {"ph": 12}}, ["soil", "ph"]),
    ({"soil": {"texture_class": "mud"}}, ["soil", "texture_class"]),
    ({"excluded_crops": ["not_a_crop"]}, ["excluded_crops", 0, "crop_id"]),
    ({"excluded_crops": [{"crop_id": "potato", "reason": "because"}]}, ["excluded_crops", 0, "reason"]),
    ({"yields_t_ha": {"not_a_crop": 3}}, ["yields_t_ha"]),
    ({"yields_t_ha": {"wheat_winter": 0}}, ["yields_t_ha", "wheat_winter"]),
    ({"history": [{"year": 2020, "crop_id": "not_a_crop"}]}, ["history", 0, "crop_id"]),
    ({"history": [{"year": 2020, "crop_id": "potato"}, {"year": 2020, "crop_id": "lentil"}]}, ["history"]),
    ({"irrigation_applied_m3_ha": {"maize_grain": 99999}}, ["irrigation_applied_m3_ha", "maize_grain"]),
    ({"irrigation_applied_m3_ha": {"nope": 100}}, ["irrigation_applied_m3_ha"]),
    ({"irrigation_method": "rain_dance"}, ["irrigation_method"]),
])
def test_details_422(details, loc_tail):
    r = client.post("/api/field/analyze", json={"field_details": details})
    assert r.status_code == 422
    locs = [e["loc"] for e in r.json()["detail"]]
    assert ["body", "field_details", *loc_tail] in locs, locs


# ---------------------------------------------------------------- soil override (unit + report)
def test_texture_table_round_trips_and_override():
    for cls, (c, s) in TEXTURE_CLAY_SAND.items():
        assert soil_mod.usda_texture_class(s, 100 - c - s, c) == cls
    sp = soil_mod.default_profile(37.6, 32.75)
    only_class = override_soil(sp, {"texture_class": "sandy loam"})
    assert (only_class.clay_pct, only_class.sand_pct) == TEXTURE_CLAY_SAND["sandy loam"]
    assert only_class.taw_mm_per_m != sp.taw_mm_per_m and only_class.source_id == "user"
    one = override_soil(sp, {"sand_pct": 95})  # inferred clay is shrunk so clay + sand <= 100
    assert one.sand_pct == 95 and one.clay_pct + one.sand_pct <= 100


@pytest.fixture(scope="module")
def combo(default):
    yrs = [y for y in default["field_memory"]["years"] if y["pattern"] in ("winter_crop", "summer_crop")][-3:]
    assert len(yrs) == 3
    crop = {"winter_crop": "wheat_winter", "summer_crop": "maize_grain"}
    hist = [{"year": y["year"], "crop_id": crop[y["pattern"]]} for y in yrs]
    other = "maize_grain" if hist[2]["crop_id"] == "wheat_winter" else "wheat_winter"
    hist[2]["crop_id"] = other  # deliberately disagrees with the satellite
    details = {"soil": {"texture_class": "clay loam", "clay_pct": 38, "sand_pct": 22, "soc_gkg": 9, "ph": 7.9},
               "excluded_crops": ["sunflower", {"crop_id": "maize_grain", "reason": "no_buyer"}],
               "history": hist, "irrigation_applied_m3_ha": {"maize_grain": 6500, "lentil": 100}}
    return build_field_report({**REQ, "field_details": details}), hist


def test_soil_override(default, combo):
    rep, _ = combo
    assert rep["soil"]["source_id"] == "user"
    assert rep["soil"]["taw_mm_per_m"] != default["soil"]["taw_mm_per_m"]
    assert rep["soil"]["clay_pct"] == 38 and rep["soil"]["sand_pct"] == 22 and rep["soil"]["silt_pct"] == 40
    assert rep["soil"]["texture_class"] == "clay loam" and rep["soil"]["ph"] == 7.9
    assert any(s["id"] == "user" for s in rep["sources"])
    fact = next(f for f in rep["facts"] if f["text"]["en"].startswith("The soil is"))
    assert fact["source_id"] == "user"
    ui = next(u for u in rep["user_inputs"] if u["id"] == "soil")
    assert ui["model"] and "SoilGrids" in ui["model"]["en"] and "killi tın" in ui["value"]["tr"]
    assert next(f for f in rep["facts"] if f["id"] == ui["fact"])["source_id"] == "user"
    _fact_ids_ok(rep)


def test_excluded_crops(combo):
    rep, _ = combo
    base, rest = rep["strategies"][0], rep["strategies"][1:]
    assert any(s["crop_id"] == "maize_grain" for s in base["steps"])  # user's own rotation unchanged
    assert rest
    assert any(not _keeps_current(s) for s in rest)
    for s in rest:
        if not _keeps_current(s):
            assert not {"sunflower", "maize_grain"} & {x["crop_id"] for x in s["steps"]}
        last = next(w for w in s["evidence"]["why"] if "Left out" in w["text"]["en"])
        assert "Sunflower" in last["text"]["en"] and "no buyer" in last["text"]["en"]
        assert "Ayçiçeği" in last["text"]["tr"]
        assert len(s["evidence"]["why"]) <= 5
        assert next(f for f in rep["facts"] if f["id"] == last["facts"][0])["source_id"] == "user"
    assert not any("Left out" in w["text"]["en"] for w in base["evidence"]["why"])


def test_excluded_cover_crops_never_used():
    rep = get_field_report({**REQ, "field_details": {"excluded_crops": ["rye_cover", "vetch_cover"]}})
    for s in rep["strategies"][1:]:
        assert not {"rye_cover", "vetch_cover"} & {x["crop_id"] for x in s["steps"]}
        assert not {"rye_cover", "vetch_cover"} & {c["crop_id"] for c in s["calendar"]}


def test_user_facts_reachable_from_evidence(combo):
    """Every fact with source_id 'user' is referenced by some evidence item (the drawer shows referenced facts)."""
    rep, _ = combo
    user = {f["id"] for f in rep["facts"] if f["source_id"] == "user"}
    refs = {fid for s in rep["strategies"] for k in ("why", "benefits", "risks")
            for it in s["evidence"][k] for fid in it.get("facts", [])}
    assert user and user <= refs | {next(f["id"] for f in rep["facts"] if f["text"]["en"].startswith("The soil is"))}


def test_empty_polygon_object_is_not_given():
    c = TestClient(app)
    assert c.post("/api/field/analyze", json={**REQ, "field_polygon": {}}).status_code == 200


def test_history_check(combo):
    rep, hist = combo
    h = rep["history_check"]
    assert h["n_years"] == 3 and h["n_agree"] == 2 and h["agreement"] == pytest.approx(0.667, abs=1e-3)
    assert [y["year"] for y in h["years"]] == sorted(x["year"] for x in hist)
    assert [y["agree"] for y in h["years"]].count(False) == 1
    assert {"year", "crop_id", "declared_pattern", "satellite_pattern", "agree"} <= set(h["years"][0])


def test_history_years_without_satellite_not_counted(default):
    sat_years = {y["year"] for y in default["field_memory"]["years"]}
    missing = next((y for y in range(2000, 2026) if y not in sat_years), None)
    if missing is None:
        pytest.skip("satellite series covers every year")
    rep = build_field_report({**REQ, "field_details": {"history": [{"year": missing, "crop_id": "wheat_winter"}]}})
    h = rep["history_check"]
    assert h["n_years"] == 0 and h["n_agree"] == 0 and h["agreement"] is None
    assert h["years"][0]["satellite_pattern"] is None and h["years"][0]["agree"] is None


def test_irrigation_check(combo):
    rep, _ = combo
    chk = {c["crop_id"]: c for c in rep["irrigation_check"]}
    m = chk["maize_grain"]
    assert m["declared_m3_ha"] == 6500 and m["modelled_m3_ha"] and m["modelled_m3_ha"] > 0
    assert m["diff_pct"] == pytest.approx((6500 - m["modelled_m3_ha"]) / m["modelled_m3_ha"] * 100, abs=0.1)
    assert chk["lentil"]["modelled_m3_ha"] is None and chk["lentil"]["diff_pct"] is None


def test_user_inputs_order_and_shape(combo):
    rep, _ = combo
    assert [u["id"] for u in rep["user_inputs"]] == ["soil", "excluded_crops", "history", "irrigation_applied"]
    for u in rep["user_inputs"]:
        assert set(u["label"]) == {"en", "tr"} and set(u["value"]) == {"en", "tr"} and u["fact"].startswith("f")


# ---------------------------------------------------------------- irrigation method
def test_irrigation_method_scales_gross_water_not_net(default):
    rep = build_field_report({**REQ, "field_details": {"irrigation_method": "drip"}})
    e = IRRIGATION_EFFICIENCY["drip"]
    b0, b1 = default["strategies"][0]["indicators"], rep["strategies"][0]["indicators"]
    assert _p50(b1["water_m3_ha_yr"]) == pytest.approx(_p50(b0["water_m3_ha_yr"]) / e, rel=1e-9)
    assert b1["irrigation_mm_yr"] == b0["irrigation_mm_yr"]
    assert _p50(b1["income_usd_ha_yr"]) < _p50(b0["income_usd_ha_yr"])  # water cost is gross
    assert rep["irrigation"] == {"method": "drip", "efficiency": 0.9, "source_id": "irrigation_efficiency"}
    assert any(s["id"] == "irrigation_efficiency" for s in rep["sources"])
    assert [u["id"] for u in rep["user_inputs"]] == ["irrigation_method"]
    _fact_ids_ok(rep)


# ---------------------------------------------------------------- water quota + polygon
@pytest.fixture(scope="module")
def quota_rep(default):
    poly = _rect(32.749, 37.599, 0.002, 0.002)
    area = normalize_polygon(poly)["area_ha"]
    q_ha = 3000.0
    rep = build_field_report({**REQ, "field_polygon": poly, "field_details": {"water_quota_m3_yr": q_ha * area}})
    return rep, area, q_ha


def test_polygon_in_report(quota_rep):
    rep, area, _ = quota_rep
    assert rep["location"]["area_ha"] == pytest.approx(area, abs=0.005)
    assert rep["location"]["polygon"]["type"] == "Polygon" and len(rep["location"]["polygon"]["coordinates"][0]) == 5
    assert rep["location"]["lat"] == pytest.approx(37.600, abs=1e-9) and rep["location"]["lon"] == pytest.approx(32.750, abs=1e-9)
    assert rep["user_inputs"][0]["id"] == "polygon" and rep["user_inputs"][0]["model"] is None
    for s in rep["strategies"]:
        assert any("30 m HLS" in g["text"]["en"] and "HLS" in g["text"]["tr"] for g in s["evidence"]["gaps"])
    _fact_ids_ok(rep)


def test_quota_filters_and_flags_baseline(quota_rep):
    rep, area, q_ha = quota_rep
    q = rep["quota"]
    assert q["basis"] == "field_total" and q["quota_m3_ha_yr"] == pytest.approx(q_ha, abs=0.1)
    assert q["quota_m3_yr"] == pytest.approx(q_ha * area)
    base = rep["strategies"][0]
    assert _p50(base["indicators"]["water_m3_ha_yr"]) > q_ha and base["exceeds_quota"] is True and q["baseline_exceeds"] is True
    assert any(r_["check_with"] == "extension_service" and "quota" in r_["text"]["en"] for r_ in base["evidence"]["risks"])
    for s in rep["strategies"][1:]:
        assert (_p50(s["indicators"]["water_m3_ha_yr"]) <= q_ha) or s["exceeds_quota"] is True
        assert s["exceeds_quota"] == (_p50(s["indicators"]["water_m3_ha_yr"]) > q_ha)
    if not q["relaxed"]:
        assert all(s["exceeds_quota"] is False for s in rep["strategies"][1:] if not _keeps_current(s))
    assert all(s["exceeds_quota"] is True for s in rep["strategies"][1:] if _keeps_current(s))  # honest flag, not hidden
    _fact_ids_ok(rep)


def test_quota_without_polygon_is_per_ha():
    rep = get_field_report({**REQ, "field_details": {"water_quota_m3_yr": 0}})
    q = rep["quota"]
    assert q["basis"] == "per_ha" and q["quota_m3_ha_yr"] == 0 and q["baseline_exceeds"] is True
    assert "area_ha" not in rep["location"]
    for s in rep["strategies"][1:]:  # quota 0 -> access "none": rain-fed only (except cards keeping the current rotation)
        if _keeps_current(s):
            assert s["exceeds_quota"] is True
            continue
        assert s["exceeds_quota"] is False
        assert all(x["irrigation"] == "none" for x in s["steps"])


def test_quota_replaces_water_access_and_irrigated_share():
    """A quota bounds irrigation on its own: water_access 'none' / share 0 in the request no longer apply."""
    req = {**REQ, "constraints": {"water_access": "none", "max_irrigated_share": 0.0},
           "field_details": {"water_quota_m3_yr": 20000}}
    rep = get_field_report(req)
    assert rep["quota"]["basis"] == "per_ha"
    assert any(x["irrigation"] != "none" for s in rep["strategies"][1:] for x in s["steps"])


# ---------------------------------------------------------------- declared yields
def test_yields_scale_income_and_do_not_mutate_cache(default):
    crops_before = load_crops()["wheat_winter"].economics.yield_t_ha.copy()
    rep = build_field_report({**REQ, "field_details": {"yields_t_ha": {"wheat_winter": 2.0}}})
    ref = crops_before["rainfed"]  # wheat is rain-fed in the default rotation
    yc = rep["yield_check"]
    assert len(yc) == 1 and yc[0]["crop_id"] == "wheat_winter" and yc[0]["declared_t_ha"] == 2.0
    assert yc[0]["regional_t_ha"] == pytest.approx(ref, abs=0.01)
    assert yc[0]["factor"] == pytest.approx(2.0 / ref, abs=1e-3)
    assert load_crops()["wheat_winter"].economics.yield_t_ha == crops_before
    b0, b1 = default["strategies"][0]["indicators"], rep["strategies"][0]["indicators"]
    assert _p50(b1["income_usd_ha_yr"]) < _p50(b0["income_usd_ha_yr"])
    ui = rep["user_inputs"][0]
    assert ui["id"] == "yields" and ui["model"] and "Regional reference" in ui["model"]["en"]
    _fact_ids_ok(rep)


def test_polygon_centroid_is_checked_like_a_point():
    """The polygon centroid, not the request's lat/lon, must be inside Konya and off the lakes (CONTRACTS 7)."""
    r = client.post("/api/field/analyze", json={"field_polygon": _rect(28.9, 41.0, 0.01, 0.01)})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "outside_konya"
    # lat/lon alone point at Cumra, but the polygon wins
    r = client.post("/api/field/analyze", json={"lat": 37.6, "lon": 32.75, "field_polygon": _rect(28.9, 41.0, 0.01, 0.01)})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "outside_konya"
