"""Field strategy cards built on the zone crop whitelist (METHODS §7.1).

Three cards replace the old water/soil/income archetypes on the field page (the basin view keeps them):

* ``low_risk``            whole field on a rotation of crops verified in the zone, lowest risk
* ``balanced_transition`` 75 % on the best verified rotation + 25 % on a verified specialty crop (default card)
* ``innovative``          80 % current rotation + 20 % verified specialty crop, plus official pilot crops as
                          small trial rows (5–10 %) that never enter the card's numbers

Water and soil are hard limits for every card, not separate cards: a card may not use more irrigation water
(p50) than the current rotation and may not raise erosion above it. The user's priorities only rank what passes.
Crops marked ``caution`` in the whitelist may stay if already in the current rotation but are never added.
Nothing is invented: a specialty crop without engine parameters is listed with its evidence and marked
``modeled: false``; the card's numbers then cover only the modelled share (``coverage``).
"""
from __future__ import annotations

from .rotations import _canon
from .scoring import DEFAULT_PRIORITIES, dimension_values, score

CARD_NAMES = {
    "low_risk": {"en": "Low risk and resilient", "tr": "Düşük riskli ve dayanıklı"},
    "balanced_transition": {"en": "Balanced transition", "tr": "Dengeli dönüşüm"},
    "innovative": {"en": "Innovative crop opportunity", "tr": "Yenilikçi mahsul fırsatı"},
}
CARD_ORDER = ["balanced_transition", "low_risk", "innovative"]
SPECIAL_SHARE = {"balanced_transition": 0.25, "innovative": 0.20}
SPECIAL_RANGE = {"balanced_transition": [0.20, 0.30], "innovative": [0.10, 0.30]}
PILOT_RANGE = [0.05, 0.10]
INCOME_FLOOR = 0.6  # share of baseline income a card's field rotation should keep (soft: falls back if none)


def zone_policy(whitelist: dict | None, crops: dict, baseline_ids: set) -> dict | None:
    """Allowed engine crops, specialty and pilot lists for one zone; ``None`` when the zone has no whitelist."""
    if not whitelist:
        return None
    field, caution, special, pilots = set(), set(), [], []
    for c in whitelist["crops"]:
        eng = [e for e in c.get("engine", []) if e in crops]
        rec = {"name": c["name"], "status": c["status"], "group": c["group"], "districts": c.get("districts", []),
               "note": c.get("note"), "sources": c["sources"], "engine_ids": eng, "modeled": bool(eng)}
        if c["status"] == "pilot":
            if c["group"] in ("field", "special"):
                pilots.append(rec)
        elif c["group"] == "field":
            field |= set(eng)
            if c.get("caution"):
                caution |= set(eng)
        elif c["group"] == "special":
            special.append(rec)
    allowed = field - (caution - set(baseline_ids))
    if "vetch_forage" in allowed and "vetch_cover" in crops:
        allowed.add("vetch_cover")  # a cover crop of a species verified in the zone
    return {"allowed": sorted(allowed), "exclude": sorted(set(crops) - allowed), "caution": sorted(caution),
            "special": special, "pilots": pilots}


def within_limits(ind: dict, base_ind: dict) -> bool:
    """Hard limits shared by all cards: no more irrigation water and no more erosion than the current rotation."""
    w_ok = ind["water_m3_ha_yr"]["p50"] <= base_ind["water_m3_ha_yr"]["p50"] + 1e-6
    e_ok = ind.get("erosion_rel", 1.0) <= max(base_ind.get("erosion_rel", 1.0), 1.0) + 1e-9
    return w_ok and e_ok


def blend(parts: list[tuple[float, dict]]) -> dict:
    """Area-weighted indicators of a split field. Bands are blended percentile by percentile (an approximation:
    the p50 of a sum is not the sum of p50s, but both parts see the same weather years)."""
    tot = sum(w for w, _ in parts)
    out: dict = {}
    for k in parts[0][1]:
        vals = [(w / tot, ind.get(k)) for w, ind in parts]
        if any(v is None for _, v in vals):
            continue
        first = vals[0][1]
        if isinstance(first, dict):
            out[k] = {q: sum(w * v[q] for w, v in vals) for q in first if all(q in v for _, v in vals)}
        elif isinstance(first, (int, float)) and not isinstance(first, bool):
            out[k] = sum(w * v for w, v in vals)
    return out


def _seq_key(r: dict) -> tuple:
    return _canon([(cid,) for cid in r.get("sequence", ())])


def _scored(r: dict, base_ind: dict, pr: dict) -> dict:
    s = score(r["indicators"], base_ind, pr)
    return {**r, "score": s["score"], "score_breakdown": s["breakdown"]}


def _part(share: float, kind: str, **kw) -> dict:
    return {"share": share, "kind": kind, **kw}


def pick_cards(results: list[dict], priorities: dict | None, policy: dict,
               special_results: dict[str, dict], pilot_results: dict[str, dict]) -> tuple[list[dict], dict]:
    """Baseline + up to three cards, and a ``notes`` dict explaining any card that could not be built.

    ``results[0]`` is the baseline simulation; the rest are whitelist-filtered candidates.
    ``special_results`` / ``pilot_results`` map an engine crop id to its single-crop simulation."""
    pr = priorities or DEFAULT_PRIORITIES
    base = results[0]
    bi = base["indicators"]
    bsc = score(bi, bi, pr)
    out = [{**base, "id": "baseline", "archetype": "baseline", "name": {"en": "Current rotation", "tr": "Mevcut rotasyon"},
            "rotation_id": base["id"], "score": bsc["score"], "score_breakdown": bsc["breakdown"]}]
    notes: dict = {}
    b_key = _seq_key(base)
    cands = [_scored(r, bi, pr) for r in results[1:] if r.get("feasible", True) and _seq_key(r) != b_key]
    ok = [r for r in cands if within_limits(r["indicators"], bi)]
    b_inc = dimension_values(bi)["income"]

    def keeps_income(r):
        return b_inc <= 0 or dimension_values(r["indicators"])["income"] >= INCOME_FLOOR * b_inc

    pool = [r for r in ok if keeps_income(r)] or ok
    low = min(pool, key=lambda r: (round(dimension_values(r["indicators"])["risk"], 3), -r["score"])) if pool else None
    by_score = sorted(pool, key=lambda r: -r["score"])
    best = next((r for r in by_score if low is None or _seq_key(r) != _seq_key(low)), low)
    field_part = best or out[0]  # no candidate within the limits: the transition keeps the current rotation

    # specialty options ranked by the score of their blend with each card's field part
    specials = [s for s in policy["special"]]
    modeled = [(s, special_results[s["engine_ids"][0]]) for s in specials
               if s["modeled"] and s["engine_ids"][0] in special_results]

    def best_special(field: dict, share: float, avoid: set):
        ranked = []
        for s, sim in modeled:
            ind = blend([(1 - share, field["indicators"]), (share, sim["indicators"])])
            if not within_limits(ind, bi):
                continue
            ranked.append((score(ind, bi, pr)["score"], s, sim, ind))
        ranked.sort(key=lambda x: -x[0])
        for x in ranked:
            if x[1]["name"]["en"] not in avoid:
                return x
        return ranked[0] if ranked else None

    def card(arch: str, field: dict, field_label: str, avoid: set) -> dict | None:
        share = SPECIAL_SHARE[arch]
        pick = best_special(field, share, avoid)
        field_p = _part(1 - share, "rotation", role=field_label, rotation_id=field.get("rotation_id", field["id"]),
                        modeled=True)
        if pick:
            _, s, sim, ind = pick
            sp = _part(share, "specialty", crop=s, modeled=True, share_range=SPECIAL_RANGE[arch])
            c = {**field, "indicators": ind, "coverage": 1.0}
        else:
            sp = _part(share, "specialty", crop=None, modeled=False, share_range=SPECIAL_RANGE[arch],
                       options=[s for s in specials if not s["modeled"]])
            c = {**field, "coverage": 1 - share}
        sc = score(c["indicators"], bi, pr)
        c.update({"id": arch, "archetype": arch, "name": CARD_NAMES[arch], "rotation_id": field.get("rotation_id", field["id"]),
                  "score": sc["score"], "score_breakdown": sc["breakdown"], "parts": [field_p, sp]})
        return c

    cards: dict = {}
    if low:
        cards["low_risk"] = {**low, "id": "low_risk", "archetype": "low_risk", "name": CARD_NAMES["low_risk"],
                             "rotation_id": low["id"], "coverage": 1.0,
                             "parts": [_part(1.0, "rotation", role="verified_rotation", rotation_id=low["id"], modeled=True)]}
    else:
        notes["low_risk"] = "no_candidate_within_limits"
    if specials:
        cards["balanced_transition"] = card("balanced_transition", field_part,
                                            "verified_rotation" if best else "current_rotation", set())
        used = {p["crop"]["name"]["en"] for p in cards["balanced_transition"]["parts"] if p.get("crop")}
        cards["innovative"] = card("innovative", out[0], "current_rotation", used)
    else:
        notes["balanced_transition"] = "no_verified_specialty"
    pilots = []
    for p in policy["pilots"]:
        row = {"crop": p, "share_range": PILOT_RANGE, "modeled": False}
        sim = pilot_results.get(p["engine_ids"][0]) if p["modeled"] else None
        if sim:
            i = sim["indicators"]
            row.update(modeled=True, water_m3_ha_yr=i["water_m3_ha_yr"], income_usd_ha_yr=i["income_usd_ha_yr"])
        pilots.append(row)
    if "innovative" in cards:
        cards["innovative"]["trials"] = pilots
    elif pilots:
        base_c = {**out[0], "id": "innovative", "archetype": "innovative", "name": CARD_NAMES["innovative"],
                  "coverage": 1.0, "trials": pilots,
                  "parts": [_part(1.0, "rotation", role="current_rotation", rotation_id=base["id"], modeled=True)]}
        cards["innovative"] = base_c
    else:
        notes["innovative"] = "no_local_evidence"
    out += [cards[a] for a in CARD_ORDER if a in cards]
    return out, notes
