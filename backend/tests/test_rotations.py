"""WP3b: rotation simulator, candidate generation, strategy picking and scoring tests."""
from __future__ import annotations

from copy import deepcopy

import pytest

from rotacast.engine import rotations as rt
from rotacast.engine.scoring import DEFAULT_PRIORITIES, score
from tests.fixtures.wp3b_fakes import FAKE_CLIMATE, make_crops, make_soil, make_weather

YEARS = list(range(1992, 2012))


@pytest.fixture(scope="module")
def weather():
    return make_weather(1990, 2024)


@pytest.fixture(scope="module")
def soil():
    return make_soil()


@pytest.fixture(scope="module")
def crops():
    return make_crops()


def rot(rid, steps, archetype="candidate"):
    return rt.Rotation(id=rid, name={"en": rid, "tr": rid},
                       archetype=archetype, steps=[rt.RotationStep(c, i + 1, irr) for i, (c, irr) in enumerate(steps)])


BASELINE = [("wheat_winter", "none"), ("sugar_beet", "full"), ("maize_grain", "full")]
SAVER = [("wheat_winter", "none"), ("chickpea", "none"), ("barley_winter", "none")]


def test_baseline_indicator_structure(weather, soil, crops):
    r = rt.simulate_rotation(rot("baseline", BASELINE, "baseline"), weather, soil, crops, YEARS)
    ind = r["indicators"]
    assert r["feasible"] and r["cycle_years"] == 3 and len(r["calendar"]) == 3
    for key in ("irrigation_mm_yr", "water_m3_ha_yr", "yield_ratio", "stress_days_yr", "income_usd_ha_yr"):
        assert ind[key]["p10"] <= ind[key]["p50"] <= ind[key]["p90"]
    for key in ("frost_risk", "heat_risk", "pest_break"):
        assert 0.0 <= ind[key] <= 1.0
    assert ind["water_m3_ha_yr"]["p50"] == pytest.approx(10 * ind["irrigation_mm_yr"]["p50"])
    assert ind["erosion_rel"] == 1.0 and r["erosion_index"] > 0
    cal = r["calendar"]
    assert [c["crop_id"] for c in cal] == ["wheat_winter", "sugar_beet", "maize_grain"]
    assert all(len(c["sow"]) == 5 and c["sow"][2] == "-" and c["kind"] == "main" for c in cal)
    assert r["feasibility"]["n_members"] == len(YEARS)


def test_sequencing_respects_harvest_to_sow_gap(weather, soil, crops):
    # maize harvest (~early Oct) then winter wheat: wheat sowing must be >= harvest + 10 days
    r = rt.simulate_rotation(rot("mw", [("maize_grain", "full"), ("wheat_winter", "none"), ("chickpea", "none")]),
                             weather, soil, crops, YEARS)
    from datetime import date, datetime
    cal = {c["crop_id"]: c for c in r["calendar"]}
    to_d = lambda s: datetime.strptime("2001-" + s, "%Y-%m-%d").date()  # noqa: E731
    harvest_maize = to_d(cal["maize_grain"]["harvest"])
    sow_wheat = to_d(cal["wheat_winter"]["sow"])
    assert (sow_wheat - harvest_maize).days >= rt.HARVEST_TO_SOW_GAP_DAYS - 1   # medians: tolerate rounding
    assert r["feasible"]


def test_gap_check_per_member_and_infeasible_flag(weather, soil, crops):
    # a very long-season summer crop followed by winter wheat whose window closes before harvest + 10 d
    late = deepcopy(crops["maize_grain"])
    late.id = "late_maize"
    late.fao56.stage_days = (40, 60, 60, 40)
    late.gdd_to_maturity = 3500
    cr = dict(crops, late_maize=late)
    r = rt.simulate_rotation(rot("late", [("late_maize", "full"), ("wheat_winter", "none"), ("chickpea", "none")]),
                             weather, soil, cr, YEARS)
    assert r["feasible"] is False
    assert r["feasibility"]["fraction"] < rt.FEASIBLE_MIN_FRACTION
    assert r["feasibility"]["issues"]


def test_legume_rotation_higher_n_balance(weather, soil, crops):
    with_leg = rt.simulate_rotation(rot("a", SAVER), weather, soil, crops, YEARS)
    no_leg = rt.simulate_rotation(rot("b", [("wheat_winter", "none"), ("sunflower", "none"), ("barley_winter", "none")]),
                                  weather, soil, crops, YEARS)
    assert with_leg["indicators"]["n_balance_kg_ha_yr"] > no_leg["indicators"]["n_balance_kg_ha_yr"]
    assert with_leg["indicators"]["n_balance_kg_ha_yr"] == pytest.approx(40 / 3)


def test_beet_maize_needs_more_irrigation_than_pulse_cereal(weather, soil, crops):
    thirsty = rt.simulate_rotation(rot("t", BASELINE), weather, soil, crops, YEARS)
    frugal = rt.simulate_rotation(rot("f", SAVER), weather, soil, crops, YEARS)
    assert thirsty["indicators"]["water_m3_ha_yr"]["p50"] > frugal["indicators"]["water_m3_ha_yr"]["p50"] + 1500
    assert frugal["indicators"]["water_m3_ha_yr"]["p50"] == 0
    # but rainfed rotation has more stress / lower yield ratio
    assert frugal["indicators"]["stress_days_yr"]["p50"] >= thirsty["indicators"]["stress_days_yr"]["p50"]
    assert frugal["indicators"]["yield_ratio"]["p50"] < thirsty["indicators"]["yield_ratio"]["p50"]


def test_cover_crop_fills_bare_window(weather, soil, crops):
    no_cover = rt.simulate_rotation(rot("nc", SAVER), weather, soil, crops, YEARS)
    with_cover = rt.simulate_rotation(
        rot("wc", [("wheat_winter", "none"), ("vetch_cover", "none"), ("chickpea", "none"), ("barley_winter", "none")]),
        weather, soil, crops, YEARS)
    kinds = [c["kind"] for c in with_cover["calendar"]]
    assert kinds.count("cover") == 1 and kinds.count("main") == 3
    assert with_cover["cycle_years"] == 3
    a, b = with_cover["indicators"], no_cover["indicators"]
    assert a["soil_cover_days_yr"] > b["soil_cover_days_yr"]
    assert a["n_balance_kg_ha_yr"] > b["n_balance_kg_ha_yr"]
    assert a["erosion_rel"] == 1.0 and with_cover["erosion_index"] < no_cover["erosion_index"]


def test_pest_break_prefers_diverse_sequences(crops):
    div = rt.pest_break_index([crops[c] for c in ("wheat_winter", "chickpea", "sunflower")])
    mono = rt.pest_break_index([crops[c] for c in ("wheat_winter", "barley_winter", "wheat_winter")])
    assert div > mono


def test_uncovered_start_years_are_dropped(weather, soil, crops):
    r = rt.simulate_rotation(rot("x", BASELINE), weather, soil, crops, [1992, 2022, 2023, 2030])
    assert r["feasibility"]["n_members"] == 1 and r["feasibility"]["n_requested"] == 4
    assert r["feasible"] is False


def test_generate_candidates_rules(crops):
    cons = {"water_access": "limited", "max_irrigated_share": 0.5, "max_candidates": 120}
    cands = rt.generate_candidates(crops, FAKE_CLIMATE, {}, cons)
    assert 20 < len(cands) <= 120
    assert [c.id for c in cands] == [f"cand_{i:03d}" for i in range(1, len(cands) + 1)]
    for c in cands:
        mains = [crops[s.crop_id] for s in c.steps if not crops[s.crop_id].is_cover]
        n = len(mains)
        assert 3 <= n <= 4
        for i in range(n):
            a, b = mains[i], mains[(i + 1) % n]
            assert a.family != b.family
            assert not set(a.disease_groups) & set(b.disease_groups)
        assert any(m.is_legume for m in mains)
        irrigated = sum(s.irrigation != "none" for s in c.steps if not crops[s.crop_id].is_cover)
        assert irrigated / n <= 0.5 + 1e-9
    assert any(any(crops[s.crop_id].is_cover for s in c.steps) for c in cands)
    again = rt.generate_candidates(crops, FAKE_CLIMATE, {}, cons)
    assert [[(s.crop_id, s.irrigation) for s in c.steps] for c in cands] == \
           [[(s.crop_id, s.irrigation) for s in c.steps] for c in again]


def test_generate_candidates_water_access_none(crops):
    cands = rt.generate_candidates(crops, FAKE_CLIMATE, {}, {"water_access": "none", "max_candidates": 60})
    assert cands
    for c in cands:
        assert all(s.irrigation == "none" for s in c.steps)
        assert all(s.crop_id not in ("sugar_beet", "maize_grain") for s in c.steps)   # irrigation "required"


def test_climate_filter_drops_long_summer_crops(crops):
    short = {"frost": {"frost_free_days": {"p50": 150}}, "monthly_normals": FAKE_CLIMATE["monthly_normals"]}
    cands = rt.generate_candidates(crops, short, {}, {"water_access": "full", "max_candidates": 80})
    used = {s.crop_id for c in cands for s in c.steps}
    assert "sugar_beet" not in used and "wheat_winter" in used


def test_scoring_baseline_is_50_and_directional(weather, soil, crops):
    b = rt.simulate_rotation(rot("baseline", BASELINE, "baseline"), weather, soil, crops, YEARS)["indicators"]
    s = score(b, b, DEFAULT_PRIORITIES)
    assert s["score"] == pytest.approx(50.0)
    assert all(v == pytest.approx(50.0) for v in s["breakdown"].values())
    f = rt.simulate_rotation(rot("f", SAVER), weather, soil, crops, YEARS)["indicators"]
    sf = score(f, b, DEFAULT_PRIORITIES)
    assert sf["breakdown"]["water"] == pytest.approx(100.0)          # no irrigation water at all
    assert sf["breakdown"]["soil"] > 50                               # legume
    assert 0 <= sf["score"] <= 100
    only_water = score(f, b, {"water": 1, "soil": 0, "income": 0, "erosion": 0, "risk": 0})
    assert only_water["score"] == pytest.approx(100.0)


def test_pick_strategies_three_distinct_archetypes_plus_baseline(weather, soil, crops):
    base = rt.simulate_rotation(rot("baseline", BASELINE, "baseline"), weather, soil, crops, YEARS[:12])
    cands = rt.generate_candidates(crops, FAKE_CLIMATE, {}, {"water_access": "limited", "max_irrigated_share": 0.5,
                                                              "max_candidates": 60})
    results = [base] + [rt.simulate_rotation(c, weather, soil, crops, YEARS[:12],
                                             baseline_erosion_index=base["erosion_index"]) for c in cands]
    picks = rt.pick_strategies(results, DEFAULT_PRIORITIES)
    assert [p["archetype"] for p in picks] == ["baseline", "water_saver", "soil_builder", "balanced_income"]
    assert picks[0]["id"] == "baseline" and picks[0]["score"] == pytest.approx(50.0)
    seqs = {rt._seq_key(p) for p in picks}
    assert len(seqs) == 4
    for p in picks:
        assert set(p["score_breakdown"]) == {"water", "soil", "income", "erosion", "risk"}
        assert 0 <= p["score"] <= 100
    by = {p["archetype"]: p for p in picks}
    assert by["water_saver"]["indicators"]["water_m3_ha_yr"]["p50"] <= by["balanced_income"]["indicators"]["water_m3_ha_yr"]["p50"] + 1e-9
    assert by["water_saver"]["indicators"]["water_m3_ha_yr"]["p50"] < base["indicators"]["water_m3_ha_yr"]["p50"]
    from rotacast.engine.scoring import soil_composite
    assert soil_composite(by["soil_builder"]["indicators"]) >= soil_composite(by["water_saver"]["indicators"]) - 1e-9
    assert soil_composite(by["soil_builder"]["indicators"]) > soil_composite(base["indicators"])
