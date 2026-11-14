"""Zone cards: whitelist policy, hard limits, area blending and card picking (no network)."""
from __future__ import annotations

import pytest

from rotacast.engine.cards import blend, pick_cards, within_limits, zone_policy
from rotacast.knowledge.crops import load_crops

CROPS = load_crops()


def wl(crops):
    return {"crops": crops}


def c(tr, status="verified", group="field", engine=(), caution=False):
    return {"name": {"tr": tr, "en": tr}, "status": status, "group": group, "sources": ["x"], "engine": list(engine),
            **({"caution": True} if caution else {})}


def test_policy_blocks_new_caution_crops_but_keeps_current_ones():
    w = wl([c("Buğday", engine=["wheat_winter"]), c("Pancar", engine=["sugar_beet"], caution=True),
            c("Mısır", engine=["maize_grain"], caution=True), c("Kimyon", group="special"),
            c("Sorgum", status="pilot", engine=["sorghum"])])
    pol = zone_policy(w, CROPS, {"wheat_winter", "sugar_beet"})
    assert set(pol["allowed"]) == {"wheat_winter", "sugar_beet"}  # maize is caution and not in the current rotation
    assert "maize_grain" in pol["exclude"] and "potato" in pol["exclude"]
    assert [s["modeled"] for s in pol["special"]] == [False]
    assert pol["pilots"][0]["engine_ids"] == ["sorghum"]
    assert zone_policy(None, CROPS, set()) is None


def ind(water, income, eros=1.0, risk=0.1):
    return {"water_m3_ha_yr": {"p10": water * 0.9, "p50": water, "p90": water * 1.1},
            "income_usd_ha_yr": {"p10": income * 0.9, "p50": income, "p90": income * 1.1},
            "irrigation_mm_yr": {"p10": water / 10, "p50": water / 10, "p90": water / 10},
            "yield_ratio": {"p10": 0.6, "p50": 0.7, "p90": 0.8}, "stress_days_yr": {"p10": 10, "p50": 20, "p90": 30},
            "frost_risk": risk, "heat_risk": risk, "n_balance_kg_ha_yr": 0.0, "residue_index": 0.5,
            "soil_cover_days_yr": 150.0, "erosion_rel": eros, "pest_break": 0.5}


def test_limits_and_blend():
    base = ind(3000, 2000)
    assert within_limits(ind(2500, 1500), base)
    assert not within_limits(ind(3100, 2500), base)
    assert not within_limits(ind(2000, 2500, eros=1.2), base)
    b = blend([(0.75, ind(2000, 1000)), (0.25, ind(4000, 3000))])
    assert b["water_m3_ha_yr"]["p50"] == pytest.approx(2500)
    assert b["income_usd_ha_yr"]["p10"] == pytest.approx(0.9 * 1500)
    assert b["soil_cover_days_yr"] == pytest.approx(150)


def res(rid, seq, i):
    return {"id": rid, "sequence": seq, "indicators": i, "feasible": True, "steps": [{"crop_id": s} for s in seq]}


def test_pick_cards_and_notes():
    base = res("baseline", ["wheat_winter", "sugar_beet"], ind(3000, 2000))
    over = res("c1", ["wheat_winter", "potato"], ind(3500, 3000))  # breaks the water limit
    safe = res("c2", ["barley_winter", "chickpea"], ind(1500, 1500, risk=0.05))
    good = res("c3", ["wheat_winter", "chickpea"], ind(2000, 1900, risk=0.2))
    pol = zone_policy(wl([c("Buğday", engine=["wheat_winter"]), c("Kimyon", group="special"),
                          c("Sorgum", status="pilot", engine=["sorghum"])]), CROPS, set())
    sorghum = {"indicators": ind(800, 900)}
    out, notes = pick_cards([base, over, safe, good], None, pol, {}, {"sorghum": sorghum})
    by = {s["archetype"]: s for s in out}
    assert list(by) == ["baseline", "balanced_transition", "low_risk", "innovative"]
    # low risk first looks among candidates keeping >= 80 % of the current income: c2 (75 %) drops out, c3 stays
    assert by["low_risk"]["rotation_id"] == "c3"
    assert by["balanced_transition"]["rotation_id"] == "c2"  # best other candidate within the limits
    assert by["balanced_transition"]["coverage"] == pytest.approx(0.75)  # specialty crop not modelled
    assert by["innovative"]["trials"][0]["modeled"] and by["innovative"]["trials"][0]["water_m3_ha_yr"]["p50"] == 800
    assert "c1" not in {s.get("rotation_id") for s in out}
    assert notes == {}

    out, notes = pick_cards([base, over], None, zone_policy(wl([c("Buğday", engine=["wheat_winter"])]), CROPS, set()), {}, {})
    assert [s["archetype"] for s in out] == ["baseline"]
    assert notes == {"low_risk": "no_candidate_within_limits", "balanced_transition": "no_verified_specialty",
                     "innovative": "no_local_evidence"}
