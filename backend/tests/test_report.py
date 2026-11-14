import json
import os

import pytest

os.environ["ROTACAST_OFFLINE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from rotacast.api.main import app  # noqa: E402
from rotacast.report import build_field_report, normalize_request  # noqa: E402

REQ = {"lat": 37.60, "lon": 32.75}


@pytest.fixture(scope="module")
def report():
    return build_field_report(REQ)


def test_contract_keys(report):
    for k in ("location", "sources", "climate", "field_memory", "soil", "terrain", "strategies", "facts", "disclaimer"):
        assert k in report
    for k in ("annual", "monthly_normals", "frost", "water_balance", "shift"):
        assert k in report["climate"]
    assert set(report["disclaimer"]) == {"en", "tr"}
    for s in report["strategies"]:
        for k in ("id", "archetype", "name", "cycle_years", "calendar", "indicators", "score", "score_breakdown", "evidence"):
            assert k in s
        assert set(s["evidence"]) == {"why", "benefits", "gaps", "risks"}
        assert s["evidence"]["gaps"]


def test_zone_cards(report):
    archs = [s["archetype"] for s in report["strategies"]]
    assert archs == ["baseline", "balanced_transition", "low_risk", "innovative"]
    cards = report["cards"]
    assert cards["zone"] == "central"
    lim = cards["limits"]
    allowed = set(cards["allowed_crops"]) | {s["crop_id"] for s in report["strategies"][0]["steps"]} | {"vetch_cover"}
    for s in report["strategies"][1:]:
        assert {st["crop_id"] for st in s["steps"]} <= allowed  # whitelist only
        assert s["indicators"]["water_m3_ha_yr"]["p50"] <= lim["water_m3_ha_yr_max"] + 1e-6  # hard water limit
        assert abs(sum(p["share"] for p in s["parts"]) - 1) < 1e-9
    assert "trials" in report["strategies"][3]
    for s in report["strategies"][1:]:  # a water-modelled specialty share must reach the API with water_coverage
        if any(p.get("water_modeled") for p in s["parts"]):
            assert s["water_coverage"] == 1.0


def test_fact_references(report):
    ids = {f["id"] for f in report["facts"]}
    assert len(ids) == len(report["facts"])
    for s in report["strategies"]:
        for sec in ("why", "benefits"):
            for e in s["evidence"][sec]:
                assert e["facts"] and set(e["facts"]) <= ids
        for e in s["evidence"]["risks"]:
            assert set(e.get("facts", [])) <= ids
            assert e["check_with"] in ("agronomist", "extension_service", "market")
    src = {x["id"] for x in report["sources"]}
    assert {f["source_id"] for f in report["facts"]} <= src


def test_json_roundtrip(report):
    txt = json.dumps(report, allow_nan=False)
    assert json.loads(txt)["location"]["lat"] == 37.6


def test_irrigation_mode_normalized():
    rot = [{"crop_id": "sugar_beet", "irrigation": m} for m in ("none", "deficit", "full", "limited")] + [{"crop_id": "maize_grain"}]
    got = [s["irrigation"] for s in normalize_request({"current_rotation": rot})["current_rotation"]]
    assert got == ["none", "deficit", "full", "deficit", "none"]  # "limited" was silently simulated as rain-fed before


def test_unknown_irrigation_mode_rejected():
    with pytest.raises(ValueError):
        normalize_request({"current_rotation": [{"crop_id": "sugar_beet", "irrigation": "partial"}]})
    r = TestClient(app).post("/api/field/analyze", json={**REQ, "current_rotation": [{"crop_id": "sugar_beet", "irrigation": "partial"}]})
    assert r.status_code == 422


def test_api_health_and_crops():
    c = TestClient(app)
    assert c.get("/api/health").json() == {"status": "ok"}
    r = c.get("/api/crops")
    assert r.status_code == 200
    j = r.json()
    assert any(x["id"] == "wheat_winter" for x in j)
    assert {"id", "name", "category", "season", "irrigation_typical"} <= set(j[0])
