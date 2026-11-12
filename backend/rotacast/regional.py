"""Basin View: regional scenario analysis for the Konya Closed Basin (docs/PLAN.md 4.6.1, CONTRACTS section 5).

The field engine is run on a coarse network of NASA POWER grid cells (0.5 deg lat x 0.625 deg lon) that overlap
the basin bounding box and contain cropland (MODIS MCD12Q1). Per-cell results are scaled up by explicit,
documented parameters (cropland area, irrigated share, adoption rate). This is a SCENARIO analysis, not a
forecast: every assumption is a field of :class:`BasinParams` and is echoed in the output ``assumptions``.

Pipeline
--------
``power_cells`` -> ``cropland_fraction`` (MODIS) -> ``simulate_cell`` (engine) -> ``aggregate`` (pure math,
no network) -> ``grace_summary`` -> ``build_basin_report``.

Per-crop production
-------------------
The engine reports rotation-level indicators only. Per-crop yield is therefore taken from a one-step
"monoculture" run of each (crop, irrigation) pair on the same cell weather; yield (t/ha) is backed out of
the income band: ``(income_p50 + water_cost * irrigation_p50 * 10) / price``. This includes the engine's
heat/frost damage penalty but ignores rotation effects on soil water carry-over (documented limitation).
"""
from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from .connectors import grace as grace_mod
from .connectors import modis, power
from .connectors import precip as precip_mod
from .connectors import soil as soil_mod
from .connectors.cache import cached_get_json
from .engine.climate import add_et0, climate_profile
from .engine.rotations import (ARCHETYPE_NAMES, DEFAULT_WATER_COST_USD_M3, Rotation, RotationStep,
                               generate_candidates, pick_strategies, simulate_rotation)
from .engine.scoring import DEFAULT_PRIORITIES
from .knowledge.crops import load_crops

KONYA_BBOX = (32.0, 37.0, 34.5, 38.8)          # min_lon, min_lat, max_lon, max_lat
POWER_DLAT, POWER_DLON = 0.5, 0.625             # NASA POWER (MERRA-2) grid spacing, degrees
EARTH_RADIUS_KM = 6371.0088
ARCHETYPES = ("water_saver", "soil_builder", "balanced_income")
LC_WEIGHTS = {12: 1.0, 14: 0.5}                 # IGBP croplands = 1, cropland/natural vegetation mosaic = 0.5

# --- Calibrated irrigated baseline mix -------------------------------------------------------------------------
# Konya province sown area 2024 (decare = 0.1 ha), Konya Il Tarim ve Orman Mudurlugu "2026 Konya Tarimi" (TUIK data),
# Table 4: https://konya.tarimorman.gov.tr/Belgeler/kitap/%C4%B0l_Tar%C4%B1m_ve_Orman_Ocak_26_4DonemV2.pdf
STAT_YEAR = 2024
STAT_AREA_DA = {"wheat": 6_378_828, "barley": 3_517_522, "sugar_beet": 850_642, "maize_grain": 1_589_939,
                "maize_silage": 392_358, "sunflower": 534_303 + 247_210, "dry_bean": 156_718, "potato": 187_849}
STAT_SOURCE = ("Konya Il Tarim ve Orman Mudurlugu, 2026 Konya Tarimi, Tablo 4 (TUIK), 2024: "
               "https://konya.tarimorman.gov.tr/Belgeler/kitap/%C4%B0l_Tar%C4%B1m_ve_Orman_Ocak_26_4DonemV2.pdf")
# Share of each crop's area that is irrigated. Sugar beet, maize, potato and dry bean are irrigated crops in Konya
# (near 100 %; assumption). Sunflower is partly irrigated (assumption 0.3). Cereals are not targeted (see calibrate_mix).
IRRIGATED_SHARE_OF_CROP = {"sugar_beet": 1.0, "maize_grain": 1.0, "maize_silage": 1.0, "potato": 1.0,
                           "dry_bean": 1.0, "sunflower": 0.3}
# Irrigated land of Konya province: 828,948 ha (KOP Bolgesi Sosyo-Ekonomik Gostergeler, Dec 2024, quoted in the
# 2026 Konya Tarimi book); total agricultural area 18,590,788 da (TUIK 2020, same book, Table 1).
IRRIGATED_HA_KONYA, AGRI_HA_KONYA = 828_948, 1_859_079
# Representative irrigated rotations (crop, irrigation). Irrigated cereals get supplemental ("deficit") irrigation.
MIX_ROTATIONS = {
    "wheat_maize": [("wheat_winter", "deficit"), ("maize_grain", "full")],
    "wheat_beet_maize": [("wheat_winter", "deficit"), ("sugar_beet", "full"), ("maize_grain", "full")],
    "barley_sunflower_wheat": [("barley_winter", "deficit"), ("sunflower", "deficit"), ("wheat_winter", "deficit")],
    "wheat_potato_bean": [("wheat_winter", "deficit"), ("potato", "full"), ("dry_bean", "full")],
}
# statistic crop -> engine crop id used in the targets (silage maize is counted with grain maize)
TARGET_CROPS = ("sugar_beet", "maize_grain", "sunflower", "potato", "dry_bean")
CEREALS = ("wheat_winter", "barley_winter")


def target_shares() -> dict:
    """Target shares of the irrigated NON-cereal crop area (sum 1) from the Konya statistics above."""
    irr = {k: STAT_AREA_DA[k] * IRRIGATED_SHARE_OF_CROP.get(k, 0.0) for k in STAT_AREA_DA}
    irr["maize_grain"] += irr.pop("maize_silage")
    tot = sum(irr[k] for k in TARGET_CROPS)
    return {k: irr[k] / tot for k in TARGET_CROPS}


def crop_shares(rotations: dict, weights: dict) -> dict:
    """Area shares per crop of the weighted rotation mix (each rotation year = equal area); cereals aggregated as
    ``cereal``; returns {crop: share of all field area} and {crop: share of non-cereal area} under ``noncereal``."""
    area: dict[str, float] = {}
    for rid, rot in rotations.items():
        n = len(rot)
        for crop, _ in rot:
            key = "cereal" if crop in CEREALS else crop
            area[key] = area.get(key, 0.0) + weights.get(rid, 0.0) / n
    nc = sum(v for k, v in area.items() if k != "cereal") or 1.0
    return {"all": area, "noncereal": {k: v / nc for k, v in area.items() if k != "cereal"}}


def calibrate_mix(rotations: dict | None = None, targets: dict | None = None) -> dict:
    """Weights (sum 1, >= 0) of the representative rotations that best reproduce the target non-cereal crop-area
    shares (least squares, SLSQP). Returns {"weights", "target", "achieved", "cereal_share", "rmse"}."""
    from scipy.optimize import minimize
    rotations = rotations or MIX_ROTATIONS
    targets = targets or target_shares()
    ids = list(rotations)

    def shares(w):
        return crop_shares(rotations, dict(zip(ids, w)))["noncereal"]

    def loss(w):
        ach = shares(w)
        return sum((ach.get(k, 0.0) - targets.get(k, 0.0)) ** 2 for k in set(targets) | set(ach))

    best = None
    for start in (np.ones(len(ids)) / len(ids), np.eye(len(ids))[0] * 0.5 + 0.5 / len(ids)):
        r = minimize(loss, start, method="SLSQP", bounds=[(0, 1)] * len(ids),
                     constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1}])
        if best is None or r.fun < best.fun:
            best = r
    w = {i: float(max(v, 0.0)) for i, v in zip(ids, best.x)}
    tot = sum(w.values())
    w = {i: v / tot for i, v in w.items()}
    res = crop_shares(rotations, w)
    return {"weights": w, "target": targets, "achieved": res["noncereal"], "cereal_share": res["all"].get("cereal", 0.0),
            "rmse": float(math.sqrt(loss(np.array(list(w.values()))) / max(len(targets), 1)))}


@dataclass
class BasinParams:
    """All scenario assumptions in one place (each one is echoed in the report ``assumptions``)."""
    bbox: tuple = KONYA_BBOX
    min_cropland_fraction: float = 0.15
    min_overlap_frac: float = 0.05              # drop cells whose bbox overlap is < 5 % of the cell
    landcover_year: int = 2022
    # Share of cropland that is irrigated: Konya irrigated land 828,948 ha (KOP 2024) / agricultural area 1,859,079 ha
    # (TUIK 2020) = 0.446 (both quoted in the 2026 Konya Tarimi book, see STAT_SOURCE). Includes irrigated orchards, so
    # it is an upper-ish estimate for field crops; the MODIS cropland area is multiplied by it.
    irrigated_share: float = IRRIGATED_HA_KONYA / AGRI_HA_KONYA
    adoption_rates: tuple = (0.1, 0.3, 0.5)
    mix_rotations: dict = field(default_factory=lambda: {k: list(v) for k, v in MIX_ROTATIONS.items()})
    baseline_mix: dict | None = None            # {rotation_id: weight}; None -> calibrate_mix() against Konya statistics
    precip_start_year: int = 2013               # satellite rain window (13 yr overlap keeps ClimateSERV calls modest)
    precip_probe_timeout_s: float = 240.0
    precip_correction: bool = True              # bias-correct POWER rain with GPM IMERG / CHIRPS (connectors.precip)
    weather_start_year: int = 1991
    last_year: int = field(default_factory=lambda: date.today().year - 1)
    n_start_years: int = 20
    horizons: tuple = (5, 10)                   # years; trend continuation is applied to horizons >= trend_from
    trend_from_horizon: int = 10
    # Fraction of the irrigation demand change that is taken from groundwater (1.0 = all of it; assumption).
    groundwater_share: float = 1.0
    priorities: dict = field(default_factory=lambda: dict(DEFAULT_PRIORITIES))
    constraints: dict = field(default_factory=lambda: {"water_access": "limited", "max_irrigated_share": 0.5})
    max_candidates: int = 300
    max_workers: int = 4


# ------------------------------------------------------------------ geometry
def rect_area_km2(lat0: float, lat1: float, lon0: float, lon1: float) -> float:
    """Area of a lat/lon rectangle on the sphere (km2)."""
    return (EARTH_RADIUS_KM ** 2 * math.radians(lon1 - lon0)
            * abs(math.sin(math.radians(lat1)) - math.sin(math.radians(lat0))))


def power_cells(bbox: tuple = KONYA_BBOX, min_overlap_frac: float = 0.05) -> list[dict]:
    """POWER grid cells overlapping ``bbox``. Centres are at multiples of 0.5 deg lat and -180 + k*0.625 lon.
    ``bounds`` is the full cell, ``clip`` its intersection with the bbox (the area used for aggregation)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    out = []
    i0, i1 = math.floor(min_lat / POWER_DLAT) - 1, math.ceil(max_lat / POWER_DLAT) + 1
    j0, j1 = math.floor((min_lon + 180) / POWER_DLON) - 1, math.ceil((max_lon + 180) / POWER_DLON) + 1
    for i in range(i0, i1 + 1):
        clat = i * POWER_DLAT
        for j in range(j0, j1 + 1):
            clon = round(-180 + j * POWER_DLON, 4)
            b = (clon - POWER_DLON / 2, clat - POWER_DLAT / 2, clon + POWER_DLON / 2, clat + POWER_DLAT / 2)
            c = (max(b[0], min_lon), max(b[1], min_lat), min(b[2], max_lon), min(b[3], max_lat))
            if c[0] >= c[2] or c[1] >= c[3]:
                continue
            full = rect_area_km2(b[1], b[3], b[0], b[2])
            area = rect_area_km2(c[1], c[3], c[0], c[2])
            if area / full < min_overlap_frac:
                continue
            out.append({"id": f"c{clat:+06.2f}_{clon:+07.3f}", "lat": clat, "lon": clon, "bounds": b,
                        "clip": c, "area_km2": area})
    return out


# ------------------------------------------------------------------ cropland fraction (MODIS MCD12Q1)
def _lc_year(year: int) -> int:
    """Clamp ``year`` to the MCD12Q1 years available (one cached date-list call)."""
    try:
        avail = [int(d["calendar_date"][:4]) for d in modis.list_dates("MCD12Q1", 37.6, 32.75)]
        return min(max(year, min(avail)), max(avail))
    except Exception:  # noqa: BLE001
        return year


def cropland_fraction(cell: dict, year: int) -> tuple[float, int]:
    """Cropland fraction of the bbox-clipped cell: 2x2 sub-windows, each one MODIS web-service call returning
    all ~500 m pixels of a (quarter-cell) window. Class 12 counts 1.0, class 14 counts 0.5.
    Returns (fraction, n_pixels). Falls back to a 3x3 point sample (modis.fetch_landcover) on failure."""
    lo0, la0, lo1, la1 = cell["clip"]
    h_km = (la1 - la0) * 111.32
    w_km = (lo1 - lo0) * 111.32 * math.cos(math.radians((la0 + la1) / 2))
    kab, klr = max(1, round(h_km / 4)), max(1, round(w_km / 4))
    num = den = 0.0
    try:
        for fy in (0.25, 0.75):
            for fx in (0.25, 0.75):
                lat, lon = la0 + fy * (la1 - la0), lo0 + fx * (lo1 - lo0)
                payload = cached_get_json(modis.LC_SOURCE_ID, f"{modis.BASE}/MCD12Q1/subset", {
                    "latitude": round(lat, 4), "longitude": round(lon, 4), "band": "LC_Type1",
                    "startDate": f"A{year}001", "endDate": f"A{year}001",
                    "kmAboveBelow": kab, "kmLeftRight": klr})
                px = np.array(payload["subset"][0]["data"], dtype=float)
                px = px[(px >= 1) & (px <= 17)]
                num += sum(LC_WEIGHTS.get(int(v), 0.0) for v in px)
                den += px.size
        if den > 0:
            return num / den, int(den)
    except Exception:  # noqa: BLE001
        pass
    vals = []
    for fy in (0.17, 0.5, 0.83):
        for fx in (0.17, 0.5, 0.83):
            try:
                vals.append(LC_WEIGHTS.get(modis.fetch_landcover(la0 + fy * (la1 - la0), lo0 + fx * (lo1 - lo0), year), 0.0))
            except Exception:  # noqa: BLE001
                pass
    return (float(np.mean(vals)) if vals else float("nan")), len(vals)


# ------------------------------------------------------------------ engine runs per cell
def _start_years(first: int, last: int, n_main: int, n: int) -> list[int]:
    return [y for y in range(first, last + 1) if y + n_main + 1 <= last][-n:]


def _n_main(steps, crops) -> int:
    return sum(1 for s in steps if crops[s.crop_id].category != "cover") or 1


def _warm(wx: pd.DataFrame, dt: float, lat: float) -> pd.DataFrame:
    """Add ``dt`` degC to tmax/tmin/tmean and recompute ET0 (trend-continuation scenario)."""
    if not dt:
        return wx
    w = wx.drop(columns=["et0"], errors="ignore").copy()
    w.attrs = dict(wx.attrs)
    for c in ("tmax", "tmin", "tmean"):
        w[c] = w[c] + dt
    return add_et0(w, lat, w.attrs.get("elevation_m", 0.0) or 0.0)


def _band(b) -> dict:
    return {k: float(b[k]) for k in ("p10", "p50", "p90")}


def _crop_yield(crop_id: str, irr: str, wx, sp, crops, ys_fn, cache: dict) -> float:
    """Single-crop yield (t/ha) from a one-step run, see the module docstring."""
    key = (crop_id, irr)
    if key not in cache:
        rot = Rotation(id=f"mono_{crop_id}_{irr}", name={"en": crop_id, "tr": crop_id}, archetype="candidate",
                       steps=[RotationStep(crop_id, 1, irr)])
        res = simulate_rotation(rot, wx, sp, crops, ys_fn(1))
        ind = res["indicators"]
        price = float(crops[crop_id].economics.price_usd_t)
        ya = (ind["income_usd_ha_yr"]["p50"] + DEFAULT_WATER_COST_USD_M3 * ind["irrigation_mm_yr"]["p50"] * 10.0) / price
        cache[key] = max(0.0, float(ya)) if res["feasibility"]["n_members"] else 0.0
    return cache[key]


def rotation_horizon(result: dict, steps: list[dict], wx, sp, crops, ys_fn, cache: dict) -> dict:
    """Water band (m3/ha/yr) and per-crop yield (t/ha per rotation-year) of a simulated rotation."""
    mains = [s for s in steps if crops[s["crop_id"]].category != "cover"]
    n = max(len(mains), 1)
    per_crop: dict[str, float] = {}
    for s in mains:
        y = _crop_yield(s["crop_id"], s["irrigation"], wx, sp, crops, ys_fn, cache) / n
        per_crop[s["crop_id"]] = per_crop.get(s["crop_id"], 0.0) + y
    return {"water_m3_ha": _band(result["indicators"]["water_m3_ha_yr"]), "crop_t_ha_yr": per_crop,
            "income_usd_ha_yr_p50": float(result["indicators"]["income_usd_ha_yr"]["p50"]),
            "yield_ratio_p50": float(result["indicators"]["yield_ratio"]["p50"])}


def simulate_cell(cell: dict, params: BasinParams, crops: dict, wx_obs: pd.DataFrame, sp) -> dict:
    """Run the baseline mix + candidates for one cell; pick archetypes (scored against the highest-weight mix
    rotation); evaluate everything under the current climate (``now``) and the trend-continuation climate
    (``trend``). Returns the per-cell input of :func:`aggregate`: ``baseline`` (list of weighted rotations) and
    ``strategies`` (archetype -> horizons)."""
    lat = cell["lat"]
    clim = climate_profile(wx_obs, lat)
    tm = next((m for m in clim["shift"]["metrics"] if m["id"] == "tmean_c"), {})
    slope = tm.get("trend_per_decade")
    dt = float(slope) if slope is not None else 0.0
    ys_fn = lambda n: _start_years(params.weather_start_year, params.last_year, n, params.n_start_years)  # noqa: E731
    weights = params.baseline_mix or calibrate_mix(params.mix_rotations)["weights"]

    base_rots = {}
    for rid, rsteps in params.mix_rotations.items():
        st = [RotationStep(c, i + 1, irr) for i, (c, irr) in enumerate(rsteps)]
        base_rots[rid] = Rotation(id=rid, name={"en": " > ".join(crops[c].name["en"] for c, _ in rsteps),
                                                "tr": " > ".join(crops[c].name["tr"] for c, _ in rsteps)},
                                  archetype="baseline", steps=st)
    ref_id = max(weights, key=weights.get)
    ref_rot = base_rots[ref_id]
    ref = simulate_rotation(ref_rot, wx_obs, sp, crops, ys_fn(_n_main(ref_rot.steps, crops)))
    bidx = ref.get("erosion_index") or None
    cands = generate_candidates(crops, clim, {}, {**params.constraints, "max_candidates": params.max_candidates})
    results = [ref] + [simulate_rotation(c, wx_obs, sp, crops, ys_fn(_n_main(c.steps, crops)),
                                         baseline_erosion_index=bidx) for c in cands]
    picked = pick_strategies(results, params.priorities)
    rot_by_id = {c.id: c for c in cands}

    wx_by = {"now": wx_obs, "trend": _warm(wx_obs, dt, lat)}
    caches = {"now": {}, "trend": {}}

    def horizons(rot, res_now, steps):
        hz = {}
        for tag in ("now", "trend"):
            res = res_now if tag == "now" else simulate_rotation(rot, wx_by[tag], sp, crops,
                                                                 ys_fn(_n_main(rot.steps, crops)),
                                                                 baseline_erosion_index=bidx)
            hz[tag] = rotation_horizon(res, steps, wx_by[tag], sp, crops, ys_fn, caches[tag])
        return hz

    baseline = []
    for rid, rot in base_rots.items():
        res = ref if rid == ref_id else simulate_rotation(rot, wx_obs, sp, crops, ys_fn(_n_main(rot.steps, crops)))
        steps = [{"crop_id": x.crop_id, "year": x.year, "irrigation": x.irrigation} for x in rot.steps]
        baseline.append({"id": rid, "weight": float(weights.get(rid, 0.0)), "name": rot.name, "steps": steps,
                         "horizons": horizons(rot, res, steps)})
    out_strats = {}
    for p in picked:
        if p["archetype"] == "baseline":
            continue
        rot = rot_by_id[p["rotation_id"]]
        out_strats[p["archetype"]] = {"score": float(p["score"]), "score_breakdown": p.get("score_breakdown"),
                                      "rotation_name": rot.name, "steps": p["steps"],
                                      "horizons": horizons(rot, p, p["steps"])}
    return {"baseline": baseline, "strategies": out_strats, "delta_t_c_per_decade": dt,
            "climate_period": clim["period"], "soil_source": sp.source_id,
            "elevation_m": wx_obs.attrs.get("elevation_m"), "n_candidates": len(cands),
            "reference_baseline": ref_id}


# ------------------------------------------------------------------ aggregation (pure math)
def _sorted_band(vals) -> dict:
    v = sorted(float(x) for x in vals)
    return {"p10": v[0], "p50": v[1], "p90": v[2]}


def mix_baseline(cell: dict, tag: str) -> dict:
    """Weight-averaged baseline of a cell: water band (m3/ha/yr) and per-crop yield (t/ha/yr)."""
    ws = sum(b["weight"] for b in cell["baseline"]) or 1.0
    water = {q: sum(b["weight"] * b["horizons"][tag]["water_m3_ha"][q] for b in cell["baseline"]) / ws
             for q in ("p10", "p50", "p90")}
    crop: dict[str, float] = {}
    for b in cell["baseline"]:
        for c, t in b["horizons"][tag]["crop_t_ha_yr"].items():
            crop[c] = crop.get(c, 0.0) + b["weight"] * t / ws
    return {"water_m3_ha": water, "crop_t_ha_yr": crop}


def aggregate(cells: list[dict], params: BasinParams, crop_names: dict | None = None,
              grace_loss_mm3: float | None = None) -> dict:
    """Scale per-cell results to the basin.

    Each cell dict needs ``irrigated_ha``; ``baseline`` = list of ``{weight, horizons}`` (the weighted baseline
    rotation mix, weights = area shares); ``strategies[arch]["horizons"]`` for the archetypes. ``horizons[tag]``
    (tag now/trend) holds ``water_m3_ha`` ({p10,p50,p90}) and ``crop_t_ha_yr`` ({crop: t/ha/yr}). A fraction ``a``
    of the irrigated area of every cell (taken proportionally from each baseline rotation) switches to the
    cell's own strategy, so a crop can only lose as much area as it holds in the baseline mix. Water band:
    same-quantile differences are summed over cells (weather assumed perfectly correlated), then ordered.
    Returns ``{"baseline": {...}, "scenarios": {arch: {rate: {horizon: {...}}}}}``."""
    crop_names = crop_names or {}
    total_irr = sum(c["irrigated_ha"] for c in cells)

    def tag_for(h):
        return "trend" if h >= params.trend_from_horizon else "now"

    base = {t: [mix_baseline(c, t) for c in cells] for t in ("now", "trend")}
    base_water = {q: sum(c["irrigated_ha"] * b["water_m3_ha"][q] for c, b in zip(cells, base["now"])) / 1e6
                  for q in ("p10", "p50", "p90")}
    base_prod: dict[str, float] = {}
    for c, b in zip(cells, base["now"]):
        for crop, t in b["crop_t_ha_yr"].items():
            base_prod[crop] = base_prod.get(crop, 0.0) + c["irrigated_ha"] * t
    out: dict = {}
    for arch in ARCHETYPES:
        idx = [i for i, c in enumerate(cells) if arch in c["strategies"]]
        out[arch] = {}
        for a in params.adoption_rates:
            per_h = {}
            for h in params.horizons:
                tag = tag_for(h)
                diffs = []
                for q in ("p10", "p50", "p90"):
                    diffs.append(sum(cells[i]["irrigated_ha"] * a * (
                        cells[i]["strategies"][arch]["horizons"][tag]["water_m3_ha"][q]
                        - base[tag][i]["water_m3_ha"][q]) for i in idx) / 1e6)
                change = _sorted_band(diffs)
                prod: dict[str, float] = {}
                for i in idx:
                    s = cells[i]["strategies"][arch]["horizons"][tag]["crop_t_ha_yr"]
                    b = base[tag][i]["crop_t_ha_yr"]
                    for crop in set(s) | set(b):
                        prod[crop] = prod.get(crop, 0.0) + cells[i]["irrigated_ha"] * a * (s.get(crop, 0.0) - b.get(crop, 0.0))
                offset = None
                if grace_loss_mm3 and grace_loss_mm3 > 0:
                    offset = _sorted_band([-params.groundwater_share * v / grace_loss_mm3 * 100.0
                                           for v in change.values()])
                per_h[str(h)] = {
                    "climate": "trend_continuation" if tag == "trend" else "current",
                    "irrigation_change_mm3_yr": change,
                    "grace_offset_pct": offset,
                    "production_change_t_yr": [
                        {"crop_id": k, "name": crop_names.get(k, {"en": k, "tr": k}), "change_t_yr": v,
                         "baseline_t_yr": base_prod.get(k, 0.0)}
                        for k, v in sorted(prod.items(), key=lambda kv: -abs(kv[1]))],
                }
            out[arch][str(a)] = per_h
    return {"baseline": {"irrigated_ha": total_irr, "irrigation_demand_mm3_yr": base_water,
                         "production_t_yr": [{"crop_id": k, "name": crop_names.get(k, {"en": k, "tr": k}), "t_yr": v}
                                             for k, v in sorted(base_prod.items(), key=lambda kv: -kv[1])]},
            "scenarios": out}


# ------------------------------------------------------------------ GRACE
def grace_summary(bbox: tuple = KONYA_BBOX) -> dict:
    """Linear trend of the GRACE/GRACE-FO TWS anomaly over the bbox and the implied volume change.
    OLS slope with a 95 % CI using an AR(1) effective sample size; volume = trend x bbox area (cos-lat
    spherical rectangle). Returns ``available: False`` with a note when the series cannot be read."""
    min_lon, min_lat, max_lon, max_lat = bbox
    area_km2 = rect_area_km2(min_lat, max_lat, min_lon, max_lon)
    try:
        s = grace_mod.fetch_tws(bbox).dropna()
        x = s.index.year + (s.index.month - 0.5) / 12.0
        y = s.to_numpy(float)
        lr = stats.linregress(x, y)
        resid = y - (lr.intercept + lr.slope * np.asarray(x))
        r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if len(resid) > 3 else 0.0
        n_eff = max(3.0, len(y) * (1 - r1) / (1 + r1)) if r1 > 0 else float(len(y))
        se = float(np.sqrt(np.sum(resid ** 2) / (len(y) - 2) / np.sum((np.asarray(x) - np.mean(x)) ** 2)))
        se *= math.sqrt(len(y) / n_eff)
        t = float(stats.t.ppf(0.975, n_eff - 2))
        lo, hi = lr.slope - t * se, lr.slope + t * se
        to_mm3 = lambda cm: cm / 100.0 * area_km2 * 1e6 / 1e6   # cm/yr -> m * km2 -> m3 = m*1e6*km2 ; /1e6 -> Mm3  # noqa: E731
        return {
            "available": True, "source_id": grace_mod.SOURCE_ID, "bbox": list(bbox), "area_km2": area_km2,
            "period": [str(s.index.min().date()), str(s.index.max().date())], "n_months": int(len(y)),
            "trend_cm_yr": float(lr.slope), "trend_ci95_cm_yr": [float(lo), float(hi)], "r1_residual": r1,
            "volume_change_mm3_yr": to_mm3(lr.slope),
            "volume_change_ci95_mm3_yr": [to_mm3(lo), to_mm3(hi)],
            "series": [{"date": str(i.date()), "tws_cm": round(float(v), 3)} for i, v in s.items()],
            "note": {"en": "GRACE measures total water storage (groundwater, soil moisture, surface water, snow) over a "
                           "~300 km footprint; it is not groundwater alone and not field-resolved.",
                     "tr": "GRACE toplam su depolamasını (yeraltı suyu, toprak nemi, yüzey suyu, kar) ~300 km ayak izinde "
                           "ölçer; yalnızca yeraltı suyu değildir ve tarla ölçeğinde değildir."},
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "source_id": grace_mod.SOURCE_ID, "bbox": list(bbox), "area_km2": area_km2,
                "trend_cm_yr": None, "trend_ci95_cm_yr": None, "volume_change_mm3_yr": None,
                "volume_change_ci95_mm3_yr": None, "series": [],
                "note": {"en": f"GRACE data unavailable ({type(exc).__name__}); comparison omitted.",
                         "tr": f"GRACE verisi yok ({type(exc).__name__}); karşılaştırma yapılmadı."}}


# ------------------------------------------------------------------ JSON helpers
def clean(o):
    """Recursively convert to strict-JSON-safe python (numpy -> python, NaN/inf -> None, tuples -> lists)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return v if math.isfinite(v) else None
    return o


def _assumptions(p: BasinParams, mix: dict, precip: dict, plaus: dict) -> list[dict]:
    A = lambda id_, en, tr, val, src: {"id": id_, "label": {"en": en, "tr": tr}, "value": val, "source": src}  # noqa: E731
    return [
        A("adoption", "Share of irrigated fields switching to the strategy", "Stratejiye geçen sulu tarla payı",
          list(p.adoption_rates), "assumption (scenario slider)"),
        A("irrigated_share", "Irrigated share of cropland", "Ekili alanın sulu payı", p.irrigated_share,
          "828,948 ha irrigated (KOP Dec 2024) / 1,859,079 ha agricultural area (TUIK 2020), both quoted in " + STAT_SOURCE
          + "; includes irrigated orchards, so an upper-ish estimate for field crops"),
        A("baseline_mix", "Calibrated baseline: weighted mix of representative irrigated rotations",
          "Kalibre baz: temsili sulu rotasyonların ağırlıklı karışımı",
          {"rotations": {k: [{"crop_id": c, "irrigation": i} for c, i in v] for k, v in p.mix_rotations.items()},
           "weights": mix["weights"], "target_noncereal_shares": mix["target"],
           "achieved_noncereal_shares": mix["achieved"], "cereal_share_of_area": mix["cereal_share"],
           "rmse": mix["rmse"]},
          "weights solved by least squares so that non-cereal crop-area shares match Konya " + str(STAT_YEAR)
          + " statistics (grain+silage maize, sugar beet, sunflower x0.3, potato, dry bean; sown area, decare: "
          + json.dumps(STAT_AREA_DA) + "; irrigated fractions are assumptions: " + json.dumps(IRRIGATED_SHARE_OF_CROP)
          + "); cereals are not targeted (their share follows from the rotations); " + STAT_SOURCE),
        A("scenario_definition", "Scenario: the adoption fraction of each baseline rotation's area switches to the "
          "cell's archetype strategy", "Senaryo: her baz rotasyonun alanının benimseme oranı kadarı hücrenin strateji rotasyonuna geçer",
          True, "a crop can lose at most its area share in the baseline mix"),
        A("cropland_weights", "MODIS classes counted as cropland (weight)", "Ekili sayılan MODIS sınıfları (ağırlık)",
          {"12": 1.0, "14": 0.5}, f"MCD12Q1 LC_Type1 {p.landcover_year}; class 14 weight is an assumption"),
        A("min_cropland_fraction", "Minimum cropland fraction for a cell", "Hücre için asgari ekili oran",
          p.min_cropland_fraction, "assumption"),
        A("constraints", "Candidate constraints (water access / max irrigated share)", "Aday kısıtları",
          p.constraints, "assumption (field-engine demo default)"),
        A("priorities", "Strategy scoring priorities", "Strateji puanlama öncelikleri", p.priorities,
          "engine default; strategies are scored against the highest-weight baseline rotation of each cell"),
        A("start_years", "Ensemble start years per rotation", "Rotasyon başına topluluk başlangıç yılı sayısı",
          p.n_start_years, f"last {p.n_start_years} feasible start years of {p.weather_start_year}-{p.last_year}"),
        A("precip_correction", "NASA POWER rain bias-corrected to GPM IMERG / CHIRPS (monthly ratio)",
          "NASA POWER yağışı GPM IMERG / CHIRPS'e göre aylık oranla düzeltildi", precip,
          "rotacast/connectors/precip.py (ClimateSERV); factors per cell in cells[].precip_correction"),
        A("trend", "Warming added for horizons >= %d years" % p.trend_from_horizon,
          "%d yıl ve üzeri ufuklarda eklenen ısınma" % p.trend_from_horizon,
          "per-cell Sen slope of annual mean temperature per decade x 1 decade",
          "trend continuation scenario, not a climate projection"),
        A("steady_state", "Production/water changes are steady-state annual rates at the horizon",
          "Üretim/su değişimi ufuktaki kararlı yıllık orandır", True,
          "adoption is immediate; no ramp, no price or area feedback"),
        A("groundwater_share", "Share of irrigation-demand change that is groundwater", "Talep değişiminin yeraltı suyu payı",
          p.groundwater_share, "assumption"),
        A("yields", "Potential yields Ym and prices", "Potansiyel verim ve fiyatlar", "crops.yaml",
          "rotacast/knowledge/crops.yaml; engine water stress applied"),
        A("plausibility_irrigation", "Plausibility check: modelled baseline irrigation demand vs published basin figures",
          "Makullük kontrolü: modellenen baz sulama talebi ve yayımlanmış havza rakamları", plaus,
          "published figures are secondary/unverified: ~2.8 bcm/yr groundwater and ~3.7 bcm/yr total irrigation withdrawal, "
          ">4.5 bcm/yr total extraction vs ~2.4 bcm/yr allowed (literature summaries, not primary DSI data); "
          "~1.9 bcm/yr abstraction from the two main irrigation zones (University of Twente MSc thesis, "
          "https://essay.utwente.nl/essays/93328). Model value is crop net irrigation requirement, which is lower than "
          "abstraction (efficiency losses, orchards, non-field uses)."),
    ]


def _limitations(precip_ok: bool) -> list[dict]:
    extra = [] if precip_ok else [{"en": "Satellite rain bias correction was not applied to all cells (service unavailable); raw NASA POWER rain was used there.",
                                    "tr": "Uydu yağış düzeltmesi tüm hücrelere uygulanamadı (servis yok); orada ham NASA POWER yağışı kullanıldı."}]
    return LIMITATIONS + extra


LIMITATIONS = [
    {"en": "The baseline is a mix of 4 representative irrigated rotations calibrated to Konya province crop-area statistics (non-cereal shares only); real farms deviate, and the statistics cover the whole province rather than the bbox.",
     "tr": "Baz, Konya il ürün alanı istatistiklerine kalibre 4 temsili sulu rotasyonun karışımıdır (yalnızca tahıl dışı paylar); gerçek işletmeler farklıdır ve istatistikler sınır kutusunu değil tüm ili kapsar."},
    {"en": "Scenario analysis, not a forecast: all results scale with the stated assumptions.",
     "tr": "Senaryo analizidir, tahmin değil: tüm sonuçlar belirtilen varsayımlarla ölçeklenir."},
    {"en": "The basin is approximated by its bounding box (32.0-34.5E, 37.0-38.8N) with a cropland filter; it is not the hydrological boundary.",
     "tr": "Havza, sınır kutusu (32.0-34.5D, 37.0-38.8K) ve ekili alan filtresiyle yaklaşıklanmıştır; hidrolojik sınır değildir."},
    {"en": "One weather series and one soil profile per 0.5x0.625 deg cell; sub-cell variability is not represented.",
     "tr": "0,5x0,625 derecelik hücre başına tek hava serisi ve tek toprak profili; hücre içi çeşitlilik temsil edilmez."},
    {"en": "Irrigation demand is crop net irrigation requirement at field level; abstraction, efficiency losses, return flows and surface-water use are not modelled.",
     "tr": "Sulama talebi tarla düzeyinde net bitki sulama ihtiyacıdır; çekim, verim kayıpları, dönüş akışı ve yüzey suyu modellenmez."},
    {"en": "GRACE is total water storage over a coarse footprint; the offset percentage is an order-of-magnitude comparison.",
     "tr": "GRACE kaba bir ayak izinde toplam su depolamasıdır; kapatma yüzdesi büyüklük mertebesi karşılaştırmasıdır."},
    {"en": "Per-crop yields come from single-crop runs on the cell weather and ignore rotation effects on soil water; production is potential-yield based, not calibrated to statistics (FAOSTAT/TUIK).",
     "tr": "Ürün verimleri hücre havasıyla tek ürünlü koşulardan gelir, rotasyonun toprak suyuna etkisini yok sayar; TÜİK/FAOSTAT'a kalibre edilmemiştir."},
    {"en": "The 10-year run adds the observed warming trend only (trend continuation); no precipitation change, CO2 effect or adaptation.",
     "tr": "10 yıllık koşu yalnızca gözlenen ısınma eğilimini ekler; yağış değişimi, CO2 etkisi ve uyum yoktur."},
    {"en": "Water-band quantiles are summed across cells assuming perfectly correlated weather (conservative width).",
     "tr": "Su bandı yüzdelikleri hücreler arası tam ilişkili hava varsayımıyla toplanır (geniş bant)."},
]

SOURCES = [
    {"id": "nasa_power", "name": "NASA POWER", "url": "https://power.larc.nasa.gov/"},
    {"id": "modis_mcd12q1", "name": "MODIS MCD12Q1 land cover", "url": "https://modis.ornl.gov/data/modis_webservice.html"},
    {"id": "grace_csr_mascon", "name": "CSR GRACE/GRACE-FO RL06.3 mascons", "url": "https://download.csr.utexas.edu/outgoing/grace/RL0603_mascons/"},
    {"id": "soilgrids", "name": "ISRIC SoilGrids 2.0 / documented regional default", "url": "https://soilgrids.org/"},
    {"id": "fao56", "name": "FAO Irrigation and Drainage Paper 56", "url": "https://www.fao.org/4/x0490e/x0490e00.htm"},
]


# ------------------------------------------------------------------ orchestration
def build_basin_report(params: BasinParams | None = None, log=print) -> dict:
    p = params or BasinParams()
    crops = load_crops()
    for rot in p.mix_rotations.values():
        for c, _ in rot:
            if c not in crops:
                raise ValueError(f"unknown crop_id: {c}")
    mix = calibrate_mix(p.mix_rotations) if p.baseline_mix is None else {
        "weights": dict(p.baseline_mix), "target": target_shares(),
        "achieved": crop_shares(p.mix_rotations, p.baseline_mix)["noncereal"],
        "cereal_share": crop_shares(p.mix_rotations, p.baseline_mix)["all"].get("cereal", 0.0), "rmse": float("nan")}
    p.baseline_mix = mix["weights"]
    log("baseline mix: " + ", ".join(f"{k}={v:.2f}" for k, v in mix["weights"].items())
        + f" (rmse {mix['rmse']:.3f}, cereal share {mix['cereal_share']:.2f})")
    cells = power_cells(p.bbox, p.min_overlap_frac)
    year = _lc_year(p.landcover_year)
    log(f"{len(cells)} POWER cells overlap the bbox; MODIS land cover year {year}")
    with ThreadPoolExecutor(max_workers=min(p.max_workers, 4)) as ex:
        fr = list(ex.map(lambda c: cropland_fraction(c, year), cells))
    for c, (f, n) in zip(cells, fr):
        c["cropland_fraction"], c["lc_pixels"] = f, n
    kept = [c for c in cells if c["cropland_fraction"] == c["cropland_fraction"]
            and c["cropland_fraction"] > p.min_cropland_fraction]
    log(f"{len(kept)} cells with cropland fraction > {p.min_cropland_fraction}")

    precip_on, precip_reason = p.precip_correction, "disabled"
    if precip_on and kept:
        # circuit breaker: ClimateSERV is often down; probe one cell in a daemon thread and give up after a timeout
        box: dict = {}

        def probe():
            try:
                box["sat"] = precip_mod.fetch_precip_daily(kept[0]["lat"], kept[0]["lon"], date(p.precip_start_year, 1, 1),
                                                           date(p.last_year, 12, 31))
            except Exception as exc:  # noqa: BLE001
                box["err"] = str(exc)[:160]
        th = threading.Thread(target=probe, daemon=True)
        th.start()
        th.join(p.precip_probe_timeout_s)
        if "sat" not in box:
            precip_on = False
            precip_reason = box.get("err") or f"satellite rain service did not answer within {p.precip_probe_timeout_s:.0f} s"
            log(f"  rain bias correction disabled: {precip_reason}")

    def load_wx(c):
        try:
            w = power.fetch_daily(c["lat"], c["lon"], date(p.weather_start_year, 1, 1), date(p.last_year, 12, 31))
        except Exception as exc:  # noqa: BLE001
            return exc
        c["precip_correction"] = {"applied": False, "reason": precip_reason}
        if precip_on:
            try:
                sat = precip_mod.fetch_precip_daily(c["lat"], c["lon"], date(p.precip_start_year, 1, 1),
                                                    date(p.last_year, 12, 31))
                w = precip_mod.bias_correct_power(w, sat)
                c["precip_correction"] = {"applied": True, **w.attrs["precip_correction"]}
            except Exception as exc:  # noqa: BLE001
                c["precip_correction"] = {"applied": False, "reason": str(exc)[:160]}
        return w
    with ThreadPoolExecutor(max_workers=min(p.max_workers, 4)) as ex:
        wxs = list(ex.map(load_wx, kept))

    names = {k: v.name for k, v in crops.items()}
    done, skipped = [], []
    for c, w in zip(kept, wxs):
        if isinstance(w, Exception):
            skipped.append({"id": c["id"], "reason": str(w)[:120]})
            log(f"  skip {c['id']}: {w}")
            continue
        elev = float(w.attrs.get("elevation_m") or 0.0)
        wx = add_et0(w, c["lat"], elev)
        wx.attrs = dict(w.attrs)
        sp = soil_mod.fetch_soil(c["lat"], c["lon"])
        sim = simulate_cell(c, p, crops, wx, sp)
        c["irrigated_ha"] = c["area_km2"] * 100.0 * c["cropland_fraction"] * p.irrigated_share
        c["cropland_ha"] = c["area_km2"] * 100.0 * c["cropland_fraction"]
        c.update(sim)
        done.append(c)
        pc = c["precip_correction"]
        log(f"  {c['id']} crop={c['cropland_fraction']:.2f} irr={c['irrigated_ha']/1e3:.0f} kha "
            f"dT={sim['delta_t_c_per_decade']:+.2f}/dec rain x{(pc['sat_mean_mm'] / pc['power_mean_mm']) if pc.get('applied') else float('nan'):.2f}")

    gr = grace_summary(p.bbox)
    loss = -gr["volume_change_mm3_yr"] if gr["available"] and gr["volume_change_mm3_yr"] is not None else None
    loss = loss if loss and loss > 0 else None
    agg = aggregate(done, p, names, loss)

    archs = [{"id": a, "name": ARCHETYPE_NAMES[a]} for a in ARCHETYPES]
    cell_out = []
    for c in done:
        st = c["strategies"]
        mb = mix_baseline(c, "now")
        b_w = mb["water_m3_ha"]["p50"]
        cands = {a: st[a]["score"] for a in ARCHETYPES if a in st}
        best = max(cands, key=cands.get) if cands else None
        cell_out.append({
            "id": c["id"], "lat": c["lat"], "lon": c["lon"], "bounds": list(c["bounds"]), "clip": list(c["clip"]),
            "area_km2": c["area_km2"], "cropland_fraction": c["cropland_fraction"], "cropland_ha": c["cropland_ha"],
            "irrigated_ha": c["irrigated_ha"], "elevation_m": c["elevation_m"], "soil_source": c["soil_source"],
            "delta_t_c_per_decade": c["delta_t_c_per_decade"], "precip_correction": c["precip_correction"],
            "baseline_water_m3_ha": b_w, "baseline_water_m3_ha_band": mb["water_m3_ha"],
            "baseline_crop_t_ha_yr": mb["crop_t_ha_yr"], "reference_baseline": c["reference_baseline"],
            "best_strategy": ({"archetype": best, "name": ARCHETYPE_NAMES[best], "score": cands[best]}
                              if best else None),
            "strategies": {a: {"score": st[a]["score"], "rotation_name": st[a]["rotation_name"], "steps": st[a]["steps"],
                               "water_change_m3_ha_p50": st[a]["horizons"]["now"]["water_m3_ha"]["p50"] - b_w,
                               "water_m3_ha": st[a]["horizons"]["now"]["water_m3_ha"],
                               "crop_t_ha_yr": st[a]["horizons"]["now"]["crop_t_ha_yr"]}
                           for a in ARCHETYPES if a in st},
        })
    dem = agg["baseline"]["irrigation_demand_mm3_yr"]["p50"]
    plaus = {"model_baseline_demand_mm3_yr_p50": dem,
             "published_total_irrigation_mm3_yr": 3690, "published_groundwater_irrigation_mm3_yr": 2790,
             "ratio_to_total": dem / 3690.0, "ratio_to_groundwater": dem / 2790.0}
    n_pc = sum(1 for c in done if c["precip_correction"].get("applied"))
    pc_summary = {"cells_corrected": n_pc, "cells_total": len(done),
                  "sources": sorted({c["precip_correction"]["source_id"] for c in done if c["precip_correction"].get("applied")})}
    log(f"baseline demand {dem:.0f} Mm3/yr = {plaus['ratio_to_total']:.2f} x published total irrigation; "
        f"rain correction applied in {n_pc}/{len(done)} cells")
    return clean({
        "schema_version": "1.1",
        "generated": date.today().isoformat(),
        "scenario_notice": {"en": "Scenario analysis, not a forecast.", "tr": "Senaryo analizidir, tahmin değildir."},
        "region": {"id": "konya_closed_basin", "name": {"en": "Konya Closed Basin", "tr": "Konya Kapalı Havzası"},
                   "bbox": list(p.bbox), "bbox_area_km2": rect_area_km2(p.bbox[1], p.bbox[3], p.bbox[0], p.bbox[2]),
                   "approximation": "bounding box + MODIS cropland filter"},
        "totals": {"n_cells": len(done), "cropland_ha": sum(c["cropland_ha"] for c in done),
                   "irrigated_ha": agg["baseline"]["irrigated_ha"], "skipped_cells": skipped},
        "baseline": {**agg["baseline"],
                     "mix": [{"id": k, "weight": mix["weights"][k],
                              "rotation": [{"crop_id": c, "irrigation": i} for c, i in p.mix_rotations[k]]}
                             for k in p.mix_rotations],
                     "target_noncereal_shares": mix["target"], "achieved_noncereal_shares": mix["achieved"],
                     "cereal_share_of_area": mix["cereal_share"]},
        "strategies": archs,
        "adoption_rates": list(p.adoption_rates),
        "horizons": list(p.horizons),
        "cells": cell_out,
        "scenarios": agg["scenarios"],
        "grace": {**gr, "loss_mm3_yr": loss},
        "assumptions": _assumptions(p, mix, pc_summary, plaus),
        "limitations": _limitations(n_pc == len(done)),
        "sources": SOURCES + [{"id": "konya_tarim_2026", "name": "Konya Il Tarim ve Orman Mudurlugu, Konya Tarimi 2026 (TUIK data)",
                               "url": "https://konya.tarimorman.gov.tr/Belgeler/kitap/%C4%B0l_Tar%C4%B1m_ve_Orman_Ocak_26_4DonemV2.pdf"},
                              {"id": "climateserv_precip", "name": "GPM IMERG / CHIRPS via ClimateSERV", "url": "https://climateserv.servirglobal.net/"}],
    })
