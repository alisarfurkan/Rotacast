"""Rotation simulator: ensemble simulation of crop sequences, candidate generation and strategy picking.

Conventions
-----------
* ``RotationStep.year`` is the cycle year in which the crop is *harvested*: for cycle start year ``Y0`` the
  year-``k`` crop is harvested in calendar year ``Y0 + k``. Spring/summer crops are sown in the spring of
  that year, winter crops in the autumn before (calendar ``Y0 + k - 1``). (Sowing winter wheat in year 1 and
  a spring crop in year 2 would otherwise collide in the field.)
* Steps are processed in list order. A step whose crop has ``category == "cover"`` is a cover crop: it is
  placed in the gap *after the preceding main crop* (a leading cover step goes into the wrap-around gap
  after the last main crop). It is sown no earlier than harvest + 10 days and terminated at least 7 days
  before the next main crop is sown (or at its own maturity, whichever is first); it is skipped for a
  member if fewer than 45 days remain.
* One main crop per cycle year. Cycle length N = number of main steps. All per-year indicators are the
  cycle totals divided by N. The accounting period of a member runs from the first sowing to the first
  sowing of the next cycle (so the wrap-around fallow is included, the spin-up fallow is not).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from . import waterbalance as wb
from .scoring import DEFAULT_PRIORITIES, dimension_values, score, soil_composite, risk_index

# Field application efficiency by irrigation method (gross water = net crop irrigation / efficiency).
# Typical values, FAO Irrigation Water Management Training Manual No. 5, Irrigation Methods (Brouwer et al., 1989) -- docs/METHODS.md.
IRRIGATION_EFFICIENCY = {"flood": 0.55, "furrow": 0.65, "sprinkler": 0.75, "drip": 0.90}

HARVEST_TO_SOW_GAP_DAYS = 10     # sowing must be >= previous harvest + 10 days
COVER_TERMINATION_LEAD_DAYS = 7  # cover crop is terminated this many days before the next main sowing
COVER_MIN_DAYS = 45              # shortest useful cover-crop season
COVER_BARE_WINDOW_DAYS = 60      # a cover crop is only inserted into bare windows of at least this length
SPINUP_DEPLETION = 0.8           # root-zone depletion fraction on 15 July of the start year (dry end of summer)
FEASIBLE_MIN_FRACTION = 0.7      # share of start years that must be sequenceable for the rotation to be feasible
DAMAGE_PENALTY_PER_DAY = 0.03    # heuristic: -3 % yield per heat/frost damage day in the sensitive stage ...
DAMAGE_PENALTY_MAX = 0.40        # ... capped at -40 %
DEFAULT_WATER_COST_USD_M3 = 0.05
DEFAULT_COVER_COST_USD_HA = 40.0  # seed + operations of a cover crop (no harvest income)
DAMAGE_DAYS_EVENT = 3            # a season counts as frost/heat hit with >= 3 damage days

ARCHETYPE_NAMES = {
    "baseline": {"en": "Current rotation", "tr": "Mevcut rotasyon"},
    "water_saver": {"en": "Water saver", "tr": "Su koruyucu"},
    "soil_builder": {"en": "Soil builder", "tr": "Toprak kurucu"},
    "balanced_income": {"en": "Balanced income", "tr": "Dengeli gelir"},
}


@dataclass
class RotationStep:
    crop_id: str
    year: int                      # cycle year (1-based), see module docstring
    irrigation: str = "none"


@dataclass
class Rotation:
    id: str
    name: dict
    archetype: str                 # baseline | water_saver | soil_builder | balanced_income | candidate
    steps: list[RotationStep] = field(default_factory=list)


# --------------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------------
def _is_cover(crop) -> bool:
    v = getattr(crop, "is_cover", None)
    return bool(v) if v is not None else getattr(crop, "category", "") == "cover"


def _is_legume(crop) -> bool:
    v = getattr(crop, "is_legume", None)
    return bool(v) if v is not None else getattr(crop, "category", "") == "legume"


def _crop_name(crop) -> dict:
    n = getattr(crop, "name", None)
    if isinstance(n, dict):
        return {"en": n.get("en", crop.id), "tr": n.get("tr", n.get("en", crop.id))}
    if n is not None and hasattr(n, "en"):
        return {"en": n.en, "tr": getattr(n, "tr", n.en)}
    return {"en": crop.id, "tr": crop.id}


def _band(x) -> dict:
    a = np.asarray(x, float)
    p10, p50, p90 = np.percentile(a, [10, 50, 90]) if a.size else (0.0, 0.0, 0.0)
    return {"p10": float(p10), "p50": float(p50), "p90": float(p90)}


def _season_len(crop) -> float:
    return float(sum(crop.fao56.stage_days))


def pest_break_index(main_crops: list) -> float:
    """0-1 index of disease/pest cycle breaking: 40 % botanical-family diversity, 40 % share of consecutive
    (cyclic) pairs with different family and no shared disease group, 20 % same for pairs two years apart."""
    n = len(main_crops)
    if n == 0:
        return 0.0
    fam_div = len({c.family for c in main_crops}) / n

    def share(dist: int) -> float:
        good = 0
        for i in range(n):
            a, b = main_crops[i], main_crops[(i + dist) % n]
            if a.family != b.family and not (set(a.disease_groups) & set(b.disease_groups)):
                good += 1
        return good / n

    s1 = share(1)
    s2 = share(2) if n >= 3 else s1
    return float(0.4 * fam_div + 0.4 * s1 + 0.2 * s2)


def _plan_sow(crop, wx, years, earliest):
    """Vectorised sowing choice. ``years`` = anchor year of the sowing window. If the window of the anchor
    year closes before ``earliest`` the next year's window is used (``delayed``). Returns (sow_idx, delayed, valid)."""
    r0, e0, v0 = wb.sow_index(crop, wx, years)
    r1, e1, v1 = wb.sow_index(crop, wx, np.asarray(years) + 1)
    use0 = v0 & (e0 >= earliest)
    use1 = (~use0) & v1 & (e1 >= earliest)
    sow = np.where(use0, np.maximum(r0, earliest), np.maximum(r1, earliest))
    return sow, use1, use0 | use1


def _clip_idx(wx, idx):
    return np.clip(idx, 0, wx.n - 1)


def _canon(seq: list[tuple]) -> tuple:
    """Canonical form of a cyclic sequence (smallest rotation)."""
    n = len(seq)
    return min(tuple(seq[i:] + seq[:i]) for i in range(n)) if n else ()


# --------------------------------------------------------------------------------------------------
# simulate_rotation
# --------------------------------------------------------------------------------------------------
def _empty_result(rotation, steps, n_requested, reason):
    zero = {"p10": 0.0, "p50": 0.0, "p90": 0.0}
    ind = {"irrigation_mm_yr": dict(zero), "water_m3_ha_yr": dict(zero), "yield_ratio": dict(zero),
           "stress_days_yr": dict(zero), "frost_risk": 0.0, "heat_risk": 0.0, "n_balance_kg_ha_yr": 0.0,
           "residue_index": 0.0, "soil_cover_days_yr": 0.0, "erosion_rel": 1.0, "pest_break": 0.0,
           "income_usd_ha_yr": dict(zero)}
    return {"id": rotation.id, "archetype": rotation.archetype, "name": rotation.name, "cycle_years": 0,
            "calendar": [], "indicators": ind, "erosion_index": 0.0, "feasible": False,
            "feasibility": {"fraction": 0.0, "n_members": 0, "n_requested": n_requested, "issues": [reason]},
            "steps": [{"crop_id": s.crop_id, "year": s.year, "irrigation": s.irrigation} for s in steps],
            "sequence": tuple(s.crop_id for s in steps if s)}


def simulate_rotation(rotation: Rotation, weather, soil, crops: dict, start_years: list[int], *,
                      baseline_erosion_index: float | None = None,
                      water_cost_usd_m3: float = DEFAULT_WATER_COST_USD_M3,
                      cover_cost_usd_ha: float = DEFAULT_COVER_COST_USD_HA,
                      irrigation_efficiency: float = 1.0) -> dict:
    """Run the rotation cycle once per start year (ensemble), carrying soil water between seasons.

    Returns a strategy-like dict: ``id, archetype, name, cycle_years, calendar, indicators`` (contract
    section 4) plus ``erosion_index`` (raw, so callers can re-normalise), ``feasible``, ``feasibility``,
    ``steps`` and ``sequence``. ``irrigation_efficiency`` (default 1.0 = net) turns net crop irrigation into
    gross water: ``water_m3_ha_yr`` and the water cost in income use gross, ``irrigation_mm_yr`` stays net;
    ``irrigation_m3_ha_by_crop`` is the mean gross m3/ha per season of each main crop. Start years whose seasons or sowing windows are not covered by ``weather``,
    or whose sequencing would force a one-year delay, are excluded from the ensemble (reported in
    ``feasibility``)."""
    wx = wb.prepare_weather(weather)
    mains: list[tuple[RotationStep, object]] = []
    covers: dict[int, tuple[RotationStep, object]] = {}
    pending_lead = []
    for st in rotation.steps:
        cr = crops[st.crop_id]
        if _is_cover(cr):
            gap = len(mains) - 1
            if gap < 0:
                pending_lead.append((st, cr))
            else:
                covers.setdefault(gap, (st, cr))
        else:
            mains.append((st, cr))
    N = len(mains)
    if N == 0:
        raise ValueError("rotation has no main crop")
    for st, cr in pending_lead[:1]:
        covers.setdefault(N - 1, (st, cr))   # leading cover = wrap-around gap
    start_years = [int(y) for y in start_years]
    M0 = len(start_years)
    y0 = np.array(start_years, dtype=np.int64)

    # ---------------- phase 1: schedule (dates only) ----------------
    spin_idx = wb._doy_idx(wx, y0, 196)  # 15 July
    ok = spin_idx >= 0
    main_sow, main_harv = [], []
    cov_sched: dict[int, tuple] = {}
    issues: list[str] = []
    prev_h = None
    for k in range(N + 1):
        crop = mains[k % N][1]
        winter = crop.season == "winter"
        anchor = y0 + k + (0 if winter else 1)
        earliest = spin_idx if prev_h is None else prev_h + HARVEST_TO_SOW_GAP_DAYS
        sow, delayed, valid = _plan_sow(crop, wx, anchor, earliest)
        bad = (~valid) | delayed
        if bad[ok].any() and k < N:
            issues.append(f"{crop.id}: sowing window closed before previous harvest + {HARVEST_TO_SOW_GAP_DAYS} d "
                          f"in {int(bad[ok].sum())} of {int(ok.sum())} start years")
        elif bad[ok].any():
            issues.append(f"{crop.id} (next cycle): sowing delayed in {int(bad[ok].sum())} start years")
        ok = ok & ~bad
        sow = _clip_idx(wx, sow)
        main_sow.append(sow)
        gap = k - 1
        if k >= 1 and gap in covers:
            ccrop = covers[gap][1]
            c_earliest = prev_h + HARVEST_TO_SOW_GAP_DAYS
            cy = wx.year[_clip_idx(wx, c_earliest)]
            c_sow, _, c_valid = _plan_sow(ccrop, wx, cy, c_earliest)
            c_sow = _clip_idx(wx, c_sow)
            _, c_total, _, c_nom = wb.season_lengths(ccrop, wx, c_sow)
            c_end = np.minimum(c_sow + c_nom, sow - COVER_TERMINATION_LEAD_DAYS)
            c_ok = c_valid & ((c_end - c_sow) >= COVER_MIN_DAYS) & (c_sow + c_nom <= wx.n)
            cov_sched[gap] = (np.where(c_ok, c_sow, sow), np.where(c_ok, c_end, sow), c_ok)
        if k < N:
            _, _, _, nominal = wb.season_lengths(crop, wx, sow)
            harv = sow + nominal
            if (harv > wx.n)[ok].any():
                issues.append(f"{crop.id}: season beyond weather end in {int((harv > wx.n)[ok].sum())} start years")
            ok = ok & (harv <= wx.n)
            main_harv.append(harv)
            prev_h = harv
    sel = np.where(ok)[0]
    n_ok = len(sel)
    frac = n_ok / M0 if M0 else 0.0
    if n_ok == 0:
        return _empty_result(rotation, rotation.steps, M0, issues[0] if issues else "no usable start year")

    # ---------------- phase 2: daily simulation, vectorised over members ----------------
    m = n_ok
    f = np.full(m, SPINUP_DEPLETION)
    cursor = spin_idx[sel]
    z = lambda: np.zeros(m)  # noqa: E731
    irr_tot, stress_tot, bare_days, erosion_sum, cover_days = z(), z(), z(), z(), z()
    income_sum, nbal = z(), z()
    yr_steps, frost_hit, heat_hit = [], [], []
    irr_gross_tot = z()
    irr_by_crop: dict[str, list[np.ndarray]] = {}
    cover_applied: dict[int, np.ndarray] = {}
    sow_rec, harv_rec = [], []
    cov_rec: dict[int, tuple] = {}

    def bare(fa):
        nonlocal bare_days, erosion_sum
        bare_days += fa["bare"]
        erosion_sum += 1.0 * fa["erosive"]   # bare soil: RUSLE C = 1

    for k in range(N + 1):
        crop = mains[k % N][1]
        sow_k = main_sow[k][sel]
        gap = k - 1
        if k >= 1 and gap in cov_sched:
            ccrop = covers[gap][1]
            c_sow, c_end, c_ok = (a[sel] for a in cov_sched[gap])
            fa = wb._fallow_core(wx, soil, cursor, c_sow, f)
            f = fa["f_end"].copy()
            bare(fa)
            sub = np.where(c_ok)[0]
            if len(sub):
                core = wb._season_core(ccrop, wx, soil, c_sow[sub], "none", f[sub], c_end[sub])
                f[sub] = core["f_end"]
                cover_days[sub] += core["cover_days"]
                erosion_sum[sub] += float(ccrop.rusle_c) * core["erosive_days"]
                nbal[sub] += float(ccrop.n_fixation_kg_ha)
                income_sum[sub] -= cover_cost_usd_ha
            cover_applied[gap] = c_ok
            cov_rec[gap] = (c_sow, c_end)
            cursor = c_end
        fa = wb._fallow_core(wx, soil, cursor, sow_k, f)
        f = fa["f_end"].copy()
        if k >= 1:
            bare(fa)
        if k >= N:
            break
        st = mains[k][0]
        core = wb._season_core(crop, wx, soil, sow_k, st.irrigation, f)
        f = core["f_end"].copy()
        cursor = core["harvest_idx"]
        sow_rec.append(sow_k)
        harv_rec.append(core["harvest_idx"])
        irr_tot += core["irr"]
        irr_g = core["irr"] / irrigation_efficiency   # gross irrigation (mm) = net / field application efficiency
        irr_gross_tot += irr_g
        irr_by_crop.setdefault(crop.id, []).append(irr_g * 10.0)
        stress_tot += core["stress"]
        cover_days += core["cover_days"]
        erosion_sum += float(crop.rusle_c) * core["erosive_days"]
        nbal += float(crop.n_fixation_kg_ha)
        yr_steps.append(core["yield_ratio"])
        frost_hit.append(core["frost"] >= DAMAGE_DAYS_EVENT)
        heat_hit.append(core["heat"] >= DAMAGE_DAYS_EVENT)
        # Ym = water-unlimited potential yield (the "irrigated" tier); the FAO-33 yield ratio
        # already carries the water stress, so rainfed crops must not also use the lower
        # rainfed tier (that would count stress twice). The "rainfed" tier is only a
        # calibration reference for modelled rainfed yields.
        pen = np.clip(DAMAGE_PENALTY_PER_DAY * (core["heat"] + core["frost"]), 0.0, DAMAGE_PENALTY_MAX)
        ya = float(crop.economics.yield_t_ha["irrigated"]) * core["yield_ratio"] * (1.0 - pen)
        income_sum += ya * float(crop.economics.price_usd_t) - water_cost_usd_m3 * irr_g * 10.0  # 1 mm = 10 m3/ha

    # ---------------- phase 3: indicators ----------------
    irr_yr = irr_tot / N
    yr_member = np.mean(np.vstack(yr_steps), axis=0)
    erosion_idx = float(np.mean(erosion_sum / N))
    erosion_rel = erosion_idx / baseline_erosion_index if baseline_erosion_index and baseline_erosion_index > 0 else 1.0
    resid_list = [float(c.residue_index) for _, c in mains]
    for gap, (_, cc) in covers.items():
        if gap in cover_applied and cover_applied[gap].mean() >= 0.5:
            resid_list.append(float(cc.residue_index))
    indicators = {
        "irrigation_mm_yr": _band(irr_yr),
        "water_m3_ha_yr": _band(irr_gross_tot / N * 10.0),
        "yield_ratio": _band(yr_member),
        "stress_days_yr": _band(stress_tot / N),
        "frost_risk": float(np.mean(np.vstack(frost_hit))),
        "heat_risk": float(np.mean(np.vstack(heat_hit))),
        # N balance: sum of the typical net N left by each crop (cover crops included), per cycle year
        "n_balance_kg_ha_yr": float(np.mean(nbal) / N),
        "residue_index": float(np.mean(resid_list)),
        "soil_cover_days_yr": float(np.mean(cover_days) / N),
        "erosion_rel": float(erosion_rel),
        "pest_break": pest_break_index([c for _, c in mains]),
        "income_usd_ha_yr": _band(income_sum / N),
    }

    # ---------------- calendar ----------------
    def md(ords_off: np.ndarray) -> str:
        d = date(2001, 1, 1) + timedelta(days=int(round(float(np.median(ords_off)))))
        return d.strftime("%m-%d")

    def offs(idx_arr, k, mask=None):
        years = y0[sel] if mask is None else y0[sel][mask]
        jan1 = np.array([date(int(y) + k, 1, 1).toordinal() for y in years])
        return idx_arr + wx.start_ord - jan1

    calendar = []
    for k, (st, cr) in enumerate(mains):
        shift = 0 if cr.season == "winter" else 1
        calendar.append({"year": st.year, "crop_id": cr.id, "crop_name": _crop_name(cr), "irrigation": st.irrigation,
                         "sow": md(offs(sow_rec[k], k + shift)), "harvest": md(offs(harv_rec[k], k + shift)),
                         "kind": "main"})
        gap = k
        if gap in cov_rec and cover_applied[gap].mean() >= 0.5:
            cs, ce = cov_rec[gap]
            sel_ok = cover_applied[gap]
            cst, cc = covers[gap]
            calendar.append({"year": st.year, "crop_id": cc.id, "crop_name": _crop_name(cc), "irrigation": "none",
                             "sow": md(offs(cs[sel_ok], k + 1, sel_ok)), "harvest": md(offs(ce[sel_ok], k + 1, sel_ok)),
                             "kind": "cover"})

    return {
        "id": rotation.id, "archetype": rotation.archetype, "name": rotation.name, "cycle_years": N,
        "calendar": calendar, "indicators": indicators, "erosion_index": erosion_idx,
        "feasible": bool(frac >= FEASIBLE_MIN_FRACTION),
        "feasibility": {"fraction": float(frac), "n_members": int(n_ok), "n_requested": int(M0), "issues": issues},
        "steps": [{"crop_id": s.crop_id, "year": s.year, "irrigation": s.irrigation} for s in rotation.steps],
        "sequence": tuple(s.crop_id for s, _ in mains),
        "irrigation_m3_ha_by_crop": {cid: float(np.mean(np.mean(np.vstack(v), axis=0))) for cid, v in irr_by_crop.items()},
    }


# --------------------------------------------------------------------------------------------------
# generate_candidates
# --------------------------------------------------------------------------------------------------
def _dig(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def _climate_suitable(crop, climate: dict) -> bool:
    """Heuristic suitability from the climate profile (CONTRACTS section 4 ``climate``).

    * Spring/summer crops: season length must fit the median frost-free period (+15 %, +30 d for frost-tolerant
      crops with frost_damage_tmin_c <= -5).
    * Winter crops: assumed extreme minimum ~ coldest monthly mean Tmin - 8 C; the crop is accepted if its
      (damage threshold - 15 C hardening allowance) is below that."""
    if not climate:
        return True
    L = _season_len(crop)
    if crop.season == "winter":
        tmins = [m.get("tmin_c") for m in (climate.get("monthly_normals") or []) if m.get("tmin_c") is not None]
        if not tmins:
            return True
        return (float(crop.frost_damage_tmin_c) - 15.0) <= (min(tmins) - 8.0)
    ff = _dig(climate, "frost", "frost_free_days", "p50")
    if ff is None:
        return True
    extra = 30.0 if float(crop.frost_damage_tmin_c) <= -5 else 0.0
    return L <= float(ff) * 1.15 + extra


def _typical_times(crop):
    """(sow_abs, harvest_abs, sow_window_end_abs) in days relative to 1 Jan of the harvest year."""
    a, b = crop.sowing.window_doy
    mid = (a + b) / 2.0
    off = -365.0 if crop.season == "winter" else 0.0
    sow = mid + off
    return sow, sow + _season_len(crop), b + off


def _can_follow(prev, nxt) -> bool:
    _, ph, _ = _typical_times(prev)
    _, _, ne = _typical_times(nxt)
    return ne + 365.0 >= ph + HARVEST_TO_SOW_GAP_DAYS


def _agronomic_ok(prev, nxt) -> bool:
    return (prev.family != nxt.family and not (set(prev.disease_groups) & set(nxt.disease_groups))
            and _can_follow(prev, nxt))


def _cover_fits(prev, nxt, cover) -> tuple[bool, float]:
    """Whether ``cover`` can be sown in the gap between ``prev`` harvest and ``nxt`` sowing; returns (fits, bare_days)."""
    _, ph, _ = _typical_times(prev)
    ns, _, _ = _typical_times(nxt)
    free_start = ph + HARVEST_TO_SOW_GAP_DAYS
    free_end = ns + 365.0 - COVER_TERMINATION_LEAD_DAYS
    bare = free_end - free_start
    a, b = cover.sowing.window_doy
    for off in (0.0, 365.0):
        lo, hi = max(free_start, a + off), min(free_end - COVER_MIN_DAYS, b + off)
        if hi >= lo:
            return True, bare
    return False, bare


def _name_of(seq_crops: list) -> dict:
    return {"en": " > ".join(_crop_name(c)["en"] for c in seq_crops),
            "tr": " > ".join(_crop_name(c)["tr"] for c in seq_crops)}


def generate_candidates(crops: dict, climate: dict, field_memory: dict, constraints: dict) -> list[Rotation]:
    """Enumerate agronomically valid 3-4 year sequences (deterministic sampling, capped).

    Rules: crops filtered by climate suitability; no same botanical family and no shared disease group in
    consecutive years (cyclic); every harvest leaves time for the next sowing window; >= 1 legume per cycle
    (when a suitable legume exists); ``water_access`` none/limited/full and ``max_irrigated_share`` bound the
    irrigated share of cycle years; cover crops are optionally inserted into bare windows >= 60 days.
    ``field_memory`` is accepted for interface symmetry (bare windows come from the crops' typical timing).
    constraints extras: ``max_candidates`` (300), ``seed`` (42), ``cycle_lengths`` ((3, 4)),
    ``exclude_crops`` (crop ids never used in generated candidates; default none)."""
    c = constraints or {}
    excluded = set(c.get("exclude_crops") or ())
    access = c.get("water_access", "limited")
    default_share = {"none": 0.0, "limited": 0.5, "full": 1.0}.get(access, 0.5)
    max_share = float(c.get("max_irrigated_share", default_share))
    if access == "none":
        max_share = 0.0
    n_max = int(c.get("max_candidates", 300))
    lengths = tuple(c.get("cycle_lengths", (3, 4)))
    rng = random.Random(int(c.get("seed", 42)))

    # Perennials (alfalfa, sainfoin) need a multi-year stand that the one-season-per-step simulator does not
    # model yet, so they are not generated as candidates (they stay usable in a user's own rotation).
    mains = [cr for _, cr in sorted(crops.items())
             if not _is_cover(cr) and _climate_suitable(cr, climate) and not getattr(cr, "perennial_years", None)
             and cr.id not in excluded]
    if access == "none":
        mains = [cr for cr in mains if getattr(cr, "irrigation_typical", "optional") != "required"]
    covers = [cr for _, cr in sorted(crops.items()) if _is_cover(cr) and _climate_suitable(cr, climate)]
    if len(mains) < 2:
        return []
    legumes = [cr for cr in mains if _is_legume(cr)]

    def irr_options(cr):
        typ = getattr(cr, "irrigation_typical", "optional")
        if access == "none":
            return ["none"]
        if typ == "none":
            return ["none"]
        if typ == "required":
            return ["full", "deficit"] if access == "full" else ["deficit"]
        return ["none", "deficit"] if access == "limited" else ["none", "deficit", "full"]

    out: list[Rotation] = []
    seen: set = set()
    attempts = 0
    while len(out) < n_max and attempts < n_max * 80:
        attempts += 1
        n = lengths[rng.randrange(len(lengths))]
        seq = [mains[rng.randrange(len(mains))]]
        fail = False
        for _ in range(n - 1):
            # A main crop appears at most once per cycle (agronomic return interval >= cycle length).
            opts = [cr for cr in mains if _agronomic_ok(seq[-1], cr) and all(s.id != cr.id for s in seq)]
            if not opts:
                fail = True
                break
            seq.append(rng.choice(opts))
        if fail or not _agronomic_ok(seq[-1], seq[0]):
            continue
        if legumes and not any(_is_legume(s) for s in seq):
            continue
        irr = [rng.choice(irr_options(s)) for s in seq]
        if sum(i != "none" for i in irr) / n > max_share + 1e-9:
            continue
        key = _canon([(s.id, i) for s, i in zip(seq, irr)])
        variants = [(key, None)]
        # optional cover-crop variant: fill every bare window >= 60 days with a fitting cover crop
        if covers and rng.random() < 0.5:
            ins = {}
            for j in range(n):
                prev, nxt = seq[j], seq[(j + 1) % n]
                fits = []
                for cv in covers:
                    ok_, bare_d = _cover_fits(prev, nxt, cv)
                    if ok_ and bare_d >= COVER_BARE_WINDOW_DAYS:
                        fits.append(cv)
                if fits:
                    ins[j] = rng.choice(fits)
            if ins:
                variants.append((key + tuple(sorted((j, cv.id) for j, cv in ins.items())) , ins))
        for vkey, ins in variants:
            if vkey in seen or len(out) >= n_max:
                continue
            seen.add(vkey)
            steps, names = [], []
            for j, (s, i) in enumerate(zip(seq, irr)):
                steps.append(RotationStep(s.id, j + 1, i))
                names.append(s)
                if ins and j in ins:
                    steps.append(RotationStep(ins[j].id, j + 1, "none"))
            nm = _name_of(names)
            if ins:
                nm = {k_: v + " (+cover)" for k_, v in nm.items()}
            out.append(Rotation(id=f"cand_{len(out) + 1:03d}", name=nm, archetype="candidate", steps=steps))
    return out


# --------------------------------------------------------------------------------------------------
# pick_strategies
# --------------------------------------------------------------------------------------------------
def _pareto_mask(vals: np.ndarray) -> np.ndarray:
    """vals: (n, d), larger is better in every column. True where the row is not dominated."""
    n = len(vals)
    keep = np.ones(n, bool)
    for i in range(n):
        ge = np.all(vals >= vals[i], axis=1)
        gt = np.any(vals > vals[i], axis=1)
        if np.any(ge & gt):
            keep[i] = False
    return keep


def _seq_key(r: dict) -> tuple:
    return _canon([(cid,) for cid in r.get("sequence", ())])


def pick_strategies(results: list[dict], priorities: dict) -> list[dict]:
    """Baseline first, then one strategy per archetype from the Pareto front over
    (water p50 down, income p50 up, soil composite up, erosion down, risk down):

    * water_saver: minimum water with income >= 60 % of the baseline (if such candidates exist)
    * soil_builder: maximum soil composite (N balance + residue + cover days)
    * balanced_income: best priority-weighted score on the Pareto front among candidates that keep >= 60 % of
      the baseline income (falls back to all candidates)
    The three picks are distinct sequences, preferring low crop-set overlap. Erosion is re-normalised to the
    baseline using each result's raw ``erosion_index``."""
    pr = priorities or DEFAULT_PRIORITIES
    base = next((r for r in results if r.get("archetype") == "baseline"), None)
    if base is None:
        raise ValueError("results must contain the baseline rotation (archetype 'baseline')")
    b_idx = base.get("erosion_index") or 0.0

    def prep(r):
        r2 = dict(r)
        ind = dict(r["indicators"])
        if b_idx > 0 and "erosion_index" in r:
            ind["erosion_rel"] = float(r["erosion_index"]) / b_idx
        r2["indicators"] = ind
        return r2

    base2 = prep(base)
    base_ind = base2["indicators"]
    base_seq = _seq_key(base)
    cands = [prep(r) for r in results if r.get("archetype") != "baseline" and r.get("feasible", True)
             and _seq_key(r) != base_seq]
    for r in cands:
        s = score(r["indicators"], base_ind, pr)
        r["score"], r["score_breakdown"] = s["score"], s["breakdown"]
    bs = score(base_ind, base_ind, pr)
    base2["score"], base2["score_breakdown"] = bs["score"], bs["breakdown"]
    base2["id"], base2["archetype"], base2["name"] = "baseline", "baseline", ARCHETYPE_NAMES["baseline"]
    base2["rotation_id"] = base["id"]
    out = [base2]
    if not cands:
        return out

    dv = [dimension_values(r["indicators"]) for r in cands]
    mat = np.array([[-d["water"], d["income"], d["soil"], -d["erosion"], -d["risk"]] for d in dv])
    front = [cands[i] for i in np.where(_pareto_mask(mat))[0]]

    chosen: list[dict] = []

    def choose(order: list[dict]):
        used_keys = {_seq_key(c) for c in chosen}
        used_sets = [set(c["sequence"]) for c in chosen]
        for r in order:
            if _seq_key(r) in used_keys:
                continue
            s = set(r["sequence"])
            if all(len(s & u) / max(len(s | u), 1) < 0.75 for u in used_sets):
                return r
        for r in order:
            if _seq_key(r) not in used_keys:
                return r
        return None

    def finish(r, archetype):
        r2 = dict(r)
        r2["rotation_id"] = r["id"]
        r2["id"], r2["archetype"], r2["name"] = archetype, archetype, ARCHETYPE_NAMES[archetype]
        out.append(r2)
        chosen.append(r)

    # water saver
    b_inc = dimension_values(base_ind)["income"]
    pool = cands
    if b_inc > 0:
        keep = [r for r in cands if dimension_values(r["indicators"])["income"] >= 0.6 * b_inc]
        pool = keep or cands
    order = sorted(pool, key=lambda r: (round(dimension_values(r["indicators"])["water"], 0),
                                        -dimension_values(r["indicators"])["income"]))
    pick = choose(order)
    if pick:
        finish(pick, "water_saver")
    # soil builder
    order = sorted(cands, key=lambda r: (-round(soil_composite(r["indicators"]), 4), -r["score"]))
    pick = choose(order)
    if pick:
        finish(pick, "soil_builder")
    # balanced income: best weighted score on the Pareto front
    # candidates that keep >= 60 % of the baseline income come first (the archetype is about *keeping* income)
    def keeps_income(r):
        return b_inc <= 0 or dimension_values(r["indicators"])["income"] >= 0.6 * b_inc
    order = (sorted([r for r in front if keeps_income(r)], key=lambda r: -r["score"])
             + sorted([r for r in cands if keeps_income(r)], key=lambda r: -r["score"])
             + sorted(front, key=lambda r: -r["score"]) + sorted(cands, key=lambda r: -r["score"]))
    pick = choose(order)
    if pick:
        finish(pick, "balanced_income")
    return out
