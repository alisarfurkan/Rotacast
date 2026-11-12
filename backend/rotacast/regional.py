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

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from .connectors import grace as grace_mod
from .connectors import modis, power
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

BASELINE_ROTATION = [("wheat_winter", "none"), ("sugar_beet", "full"), ("maize_grain", "full")]


@dataclass
class BasinParams:
    """All scenario assumptions in one place (each one is echoed in the report ``assumptions``)."""
    bbox: tuple = KONYA_BBOX
    min_cropland_fraction: float = 0.15
    min_overlap_frac: float = 0.05              # drop cells whose bbox overlap is < 5 % of the cell
    landcover_year: int = 2022
    # Share of cropland that is irrigated. Source: a Turkish study of the Konya Plain reports irrigated agriculture
    # on about one third of its 18.5 million decare (1.85 Mha) agricultural area (dergipark.org.tr/en/download/
    # article-file/4394763). The MODIS cropland area is applied to this share; treat as +-10 pts uncertain.
    irrigated_share: float = 0.33
    adoption_rates: tuple = (0.1, 0.3, 0.5)
    baseline_rotation: tuple = tuple(BASELINE_ROTATION)
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
    """Run baseline + candidates for one cell; pick archetypes; evaluate them under the current climate
    (``now``) and the trend-continuation climate (``trend``). Returns the per-cell input of :func:`aggregate`."""
    lat = cell["lat"]
    clim = climate_profile(wx_obs, lat)
    tm = next((m for m in clim["shift"]["metrics"] if m["id"] == "tmean_c"), {})
    slope = tm.get("trend_per_decade")
    dt = float(slope) if slope is not None else 0.0
    ys_fn = lambda n: _start_years(params.weather_start_year, params.last_year, n, params.n_start_years)  # noqa: E731

    steps = [RotationStep(c, i + 1, irr) for i, (c, irr) in enumerate(params.baseline_rotation)]
    base_rot = Rotation(id="baseline", name={"en": "Regional baseline", "tr": "Bölgesel baz rotasyon"},
                        archetype="baseline", steps=steps)
    base = simulate_rotation(base_rot, wx_obs, sp, crops, ys_fn(_n_main(steps, crops)))
    bidx = base.get("erosion_index") or None
    cands = generate_candidates(crops, clim, {}, {**params.constraints, "max_candidates": params.max_candidates})
    results = [base] + [simulate_rotation(c, wx_obs, sp, crops, ys_fn(_n_main(c.steps, crops)),
                                          baseline_erosion_index=bidx) for c in cands]
    picked = pick_strategies(results, params.priorities)
    rot_by_id = {c.id: c for c in cands}

    wx_trend = _warm(wx_obs, dt, lat)
    wx_by = {"now": wx_obs, "trend": wx_trend}
    caches = {"now": {}, "trend": {}}
    out_strats = {}
    for p in picked:
        arch = p["archetype"]
        if p["archetype"] == "baseline":
            rot = base_rot
        else:
            rot = rot_by_id[p["rotation_id"]]
        hz = {}
        for tag in ("now", "trend"):
            res = p if tag == "now" else simulate_rotation(rot, wx_by[tag], sp, crops,
                                                           ys_fn(_n_main(rot.steps, crops)),
                                                           baseline_erosion_index=bidx)
            hz[tag] = rotation_horizon(res, p["steps"], wx_by[tag], sp, crops, ys_fn, caches[tag])
        out_strats[arch] = {"score": float(p["score"]), "score_breakdown": p.get("score_breakdown"),
                            "rotation_name": p.get("name") if arch == "baseline" else rot.name,
                            "steps": p["steps"], "horizons": hz}
    return {"strategies": out_strats, "delta_t_c_per_decade": dt, "climate_period": clim["period"],
            "soil_source": sp.source_id, "elevation_m": wx_obs.attrs.get("elevation_m"),
            "n_candidates": len(cands)}


# ------------------------------------------------------------------ aggregation (pure math)
def _sorted_band(vals) -> dict:
    v = sorted(float(x) for x in vals)
    return {"p10": v[0], "p50": v[1], "p90": v[2]}


def aggregate(cells: list[dict], params: BasinParams, crop_names: dict | None = None,
              grace_loss_mm3: float | None = None) -> dict:
    """Scale per-cell results to the basin.

    Each cell dict needs ``irrigated_ha`` and ``strategies[arch]["horizons"][tag]`` with ``water_m3_ha``
    ({p10,p50,p90}) and ``crop_t_ha_yr`` ({crop: t/ha/yr}), for ``arch`` in baseline + archetypes, ``tag`` in
    now/trend. Adopters are a fraction ``a`` of the irrigated area of every cell and move from the baseline
    to the cell's own strategy. Water band: same-quantile differences are summed over cells (cell weather is
    assumed perfectly correlated), then ordered. Positive ``offset`` = water saved.
    Returns ``{"baseline": {...}, "scenarios": {arch: {rate: {horizon: {...}}}}}``."""
    crop_names = crop_names or {}
    total_irr = sum(c["irrigated_ha"] for c in cells)

    def tag_for(h):
        return "trend" if h >= params.trend_from_horizon else "now"

    base_water = {q: sum(c["irrigated_ha"] * c["strategies"]["baseline"]["horizons"]["now"]["water_m3_ha"][q]
                         for c in cells) / 1e6 for q in ("p10", "p50", "p90")}
    base_prod: dict[str, float] = {}
    for c in cells:
        for crop, t in c["strategies"]["baseline"]["horizons"]["now"]["crop_t_ha_yr"].items():
            base_prod[crop] = base_prod.get(crop, 0.0) + c["irrigated_ha"] * t
    out: dict = {}
    for arch in ARCHETYPES:
        have = [c for c in cells if arch in c["strategies"]]
        out[arch] = {}
        for a in params.adoption_rates:
            per_h = {}
            for h in params.horizons:
                tag = tag_for(h)
                diffs = []
                for q in ("p10", "p50", "p90"):
                    diffs.append(sum(c["irrigated_ha"] * a * (c["strategies"][arch]["horizons"][tag]["water_m3_ha"][q]
                                                              - c["strategies"]["baseline"]["horizons"][tag]["water_m3_ha"][q])
                                     for c in have) / 1e6)
                change = _sorted_band(diffs)
                prod: dict[str, float] = {}
                for c in have:
                    s, b = (c["strategies"][arch]["horizons"][tag]["crop_t_ha_yr"],
                            c["strategies"]["baseline"]["horizons"][tag]["crop_t_ha_yr"])
                    for crop in set(s) | set(b):
                        prod[crop] = prod.get(crop, 0.0) + c["irrigated_ha"] * a * (s.get(crop, 0.0) - b.get(crop, 0.0))
                offset = None
                if grace_loss_mm3 and grace_loss_mm3 > 0:
                    offset = _sorted_band([-params.groundwater_share * v / grace_loss_mm3 * 100.0
                                           for v in change.values()])
                per_h[str(h)] = {
                    "climate": "trend_continuation" if tag == "trend" else "current",
                    "irrigation_change_mm3_yr": change,
                    "grace_offset_pct": offset,
                    "production_change_t_yr": [
                        {"crop_id": k, "name": crop_names.get(k, {"en": k, "tr": k}), "change_t_yr": v}
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


def _assumptions(p: BasinParams) -> list[dict]:
    A = lambda id_, en, tr, val, src: {"id": id_, "label": {"en": en, "tr": tr}, "value": val, "source": src}  # noqa: E731
    return [
        A("adoption", "Share of irrigated fields switching to the strategy", "Stratejiye geçen sulu tarla payı",
          list(p.adoption_rates), "assumption (scenario slider)"),
        A("irrigated_share", "Irrigated share of cropland", "Ekili alanın sulu payı", p.irrigated_share,
          "Turkish Konya Plain study: ~1/3 of 1.85 Mha agricultural area irrigated (dergipark.org.tr article-file/4394763); approximate"),
        A("baseline", "Regional baseline rotation", "Bölgesel baz rotasyon",
          [{"crop_id": c, "irrigation": i} for c, i in p.baseline_rotation],
          "assumption: dominant irrigated Konya-plain rotation (winter wheat > sugar beet > grain maize)"),
        A("cropland_weights", "MODIS classes counted as cropland (weight)", "Ekili sayılan MODIS sınıfları (ağırlık)",
          {"12": 1.0, "14": 0.5}, f"MCD12Q1 LC_Type1 {p.landcover_year}; class 14 weight is an assumption"),
        A("min_cropland_fraction", "Minimum cropland fraction for a cell", "Hücre için asgari ekili oran",
          p.min_cropland_fraction, "assumption"),
        A("constraints", "Candidate constraints (water access / max irrigated share)", "Aday kısıtları",
          p.constraints, "assumption (field-engine demo default)"),
        A("priorities", "Strategy scoring priorities", "Strateji puanlama öncelikleri", p.priorities,
          "engine default"),
        A("start_years", "Ensemble start years per rotation", "Rotasyon başına topluluk başlangıç yılı sayısı",
          p.n_start_years, f"last {p.n_start_years} feasible start years of {p.weather_start_year}-{p.last_year}"),
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
    ]


LIMITATIONS = [
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
    {"id": "konya_irrigated_share", "name": "Konya Plain irrigated-area study (dergipark)", "url": "https://dergipark.org.tr/en/download/article-file/4394763"},
]


# ------------------------------------------------------------------ orchestration
def build_basin_report(params: BasinParams | None = None, log=print) -> dict:
    p = params or BasinParams()
    crops = load_crops()
    for c, _ in p.baseline_rotation:
        if c not in crops:
            raise ValueError(f"unknown crop_id: {c}")
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

    def load_wx(c):
        try:
            w = power.fetch_daily(c["lat"], c["lon"], date(p.weather_start_year, 1, 1), date(p.last_year, 12, 31))
            return w
        except Exception as exc:  # noqa: BLE001
            return exc
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
        log(f"  {c['id']} crop={c['cropland_fraction']:.2f} irr={c['irrigated_ha']/1e3:.0f} kha "
            f"dT={sim['delta_t_c_per_decade']:+.2f}/dec cands={sim['n_candidates']}")

    gr = grace_summary(p.bbox)
    loss = -gr["volume_change_mm3_yr"] if gr["available"] and gr["volume_change_mm3_yr"] is not None else None
    loss = loss if loss and loss > 0 else None
    agg = aggregate(done, p, names, loss)

    archs = [{"id": "baseline", "name": ARCHETYPE_NAMES["baseline"]}] + \
            [{"id": a, "name": ARCHETYPE_NAMES[a]} for a in ARCHETYPES]
    cell_out = []
    for c in done:
        st = c["strategies"]
        cands = {a: st[a]["score"] for a in ARCHETYPES if a in st}
        best = max(cands, key=cands.get) if cands else "baseline"
        b_w = st["baseline"]["horizons"]["now"]["water_m3_ha"]["p50"]
        cell_out.append({
            "id": c["id"], "lat": c["lat"], "lon": c["lon"], "bounds": list(c["bounds"]), "clip": list(c["clip"]),
            "area_km2": c["area_km2"], "cropland_fraction": c["cropland_fraction"], "cropland_ha": c["cropland_ha"],
            "irrigated_ha": c["irrigated_ha"], "elevation_m": c["elevation_m"], "soil_source": c["soil_source"],
            "delta_t_c_per_decade": c["delta_t_c_per_decade"],
            "baseline_water_m3_ha": b_w,
            "best_strategy": {"archetype": best, "name": ARCHETYPE_NAMES[best], "score": cands.get(best)},
            "strategies": {a: {"score": st[a]["score"], "rotation_name": st[a]["rotation_name"], "steps": st[a]["steps"],
                               "water_change_m3_ha_p50": st[a]["horizons"]["now"]["water_m3_ha"]["p50"] - b_w,
                               "water_m3_ha": st[a]["horizons"]["now"]["water_m3_ha"],
                               "crop_t_ha_yr": st[a]["horizons"]["now"]["crop_t_ha_yr"]}
                           for a in ["baseline", *ARCHETYPES] if a in st},
        })
    return clean({
        "schema_version": "1.0",
        "generated": date.today().isoformat(),
        "scenario_notice": {"en": "Scenario analysis, not a forecast.", "tr": "Senaryo analizidir, tahmin değildir."},
        "region": {"id": "konya_closed_basin", "name": {"en": "Konya Closed Basin", "tr": "Konya Kapalı Havzası"},
                   "bbox": list(p.bbox), "bbox_area_km2": rect_area_km2(p.bbox[1], p.bbox[3], p.bbox[0], p.bbox[2]),
                   "approximation": "bounding box + MODIS cropland filter"},
        "totals": {"n_cells": len(done), "cropland_ha": sum(c["cropland_ha"] for c in done),
                   "irrigated_ha": agg["baseline"]["irrigated_ha"], "skipped_cells": skipped},
        "baseline": {**agg["baseline"], "rotation": [{"crop_id": c, "irrigation": i} for c, i in p.baseline_rotation]},
        "strategies": archs,
        "adoption_rates": list(p.adoption_rates),
        "horizons": list(p.horizons),
        "cells": cell_out,
        "scenarios": agg["scenarios"],
        "grace": {**gr, "loss_mm3_yr": loss},
        "assumptions": _assumptions(p),
        "limitations": LIMITATIONS,
        "sources": SOURCES,
    })
