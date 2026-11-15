# Rotacast — Interface Contracts (v1)

Every work package builds against these contracts. Do not change a contract on your own: if you need a change, keep to the contract and report the proposed change to the orchestrator.

Conventions:
- Python 3.13, package `rotacast` under `backend/rotacast/`. Run tests from `backend/` with `python -m pytest`.
- Dates are `datetime.date` / pandas `DatetimeIndex` (naive, local solar time as POWER returns). Day-of-year (DOY) is 1–366.
- Units: temperature °C, precipitation/ET/irrigation mm (per day or per season as named), radiation MJ m⁻² day⁻¹, wind m s⁻¹ at 2 m, RH %, area ha, water volume m³.
- Missing values are `NaN`, never sentinel values like -999.
- Every data function records its provenance (`source_id`, see `docs/SOURCES.md`).
- No network calls in unit tests: use fixtures saved under `backend/tests/fixtures/`.

Demo location (Konya Plain, irrigated cropland near Çumra): **lat 37.60, lon 32.75**. A second sanity location: Kansas, USA **lat 38.50, lon -98.50**.

---

## 1. Connectors — `rotacast/connectors/`

All connectors cache raw HTTP responses on disk via `rotacast.connectors.cache` so the app works offline once data is fetched. Cache dir: `<repo>/data/cache/<source_id>/<sha1-of-request>.json` (committed to git for the demo locations).

```python
# cache.py
def cached_get_json(source_id: str, url: str, params: dict | None = None, *, timeout: float = 120, retries: int = 3) -> dict: ...
# On cache hit: return parsed JSON without network. On miss: GET with retries and exponential backoff, store, return.
# Env var ROTACAST_OFFLINE=1 → never hit the network; raise CacheMiss on miss.

# power.py  (source_id "nasa_power")
def fetch_daily(lat: float, lon: float, start: date, end: date) -> pd.DataFrame: ...
# Index: DatetimeIndex named "date", daily, continuous.
# Columns: tmax, tmin, tmean, precip, rh, wind2m, rs, gwetroot, gwettop
#   (POWER params T2M_MAX, T2M_MIN, T2M, PRECTOTCORR, RH2M, WS2M, ALLSKY_SFC_SW_DWN, GWETROOT, GWETTOP; community=AG)
# df.attrs: {"lat","lon","elevation_m","source_id":"nasa_power"}
# Must split long ranges into requests the API accepts and concatenate.

# modis.py  (source_id "modis_mod13q1" via ORNL DAAC MODIS web service, no auth)
def fetch_ndvi(lat: float, lon: float, start: date, end: date) -> pd.DataFrame: ...
# Index: DatetimeIndex "date" = composite calendar_date. Columns: ndvi (float, scaled 0.0001, -0.2..1),
# reliability (int: MOD13Q1 250m_16_days_pixel_reliability; 0 good, 1 marginal, 2 snow/ice, 3 cloudy).
# Single pixel (kmAboveBelow=0, kmLeftRight=0). Chunk requests (the service limits dates per request).

def fetch_landcover(lat: float, lon: float, year: int) -> int: ...
# MCD12Q1 LC_Type1 (IGBP) class at the pixel. 12 = croplands, 14 = cropland/natural mosaic.

# soil.py  (source_id "soilgrids", fallback "soil_default")
@dataclass
class SoilProfile:
    clay_pct: float; sand_pct: float; silt_pct: float
    soc_gkg: float           # soil organic carbon g/kg, 0–30 cm depth-weighted
    ph: float
    bulk_density: float      # g/cm³
    texture_class: str       # USDA texture class name
    fc: float; wp: float     # volumetric water content at field capacity / wilting point (m³/m³), Saxton & Rawls 2006
    taw_mm_per_m: float      # (fc - wp) * 1000
    source_id: str           # "soilgrids" | "soil_default"
def fetch_soil(lat: float, lon: float) -> SoilProfile: ...
# SoilGrids v2 REST is unreliable (returned 503 on 2026-11-12): retry, then fall back to cache,
# then to a documented default for the region (source_id "soil_default"). Never raise.

# terrain.py  (source_id "srtm_terrain_tiles": AWS Open Data terrain tiles, SRTM-derived, no auth)
def fetch_terrain(lat: float, lon: float) -> dict: ...   # {"elevation_m", "slope_pct", "source_id"}

# grace.py  (source_id "grace_csr_mascon" or other no-auth GRACE/GRACE-FO mascon source)
def fetch_tws(bbox: tuple[float, float, float, float]) -> pd.Series: ...
# bbox = (min_lon, min_lat, max_lon, max_lat). Monthly terrestrial water storage anomaly, cm equivalent water
# height, area-weighted mean over the bbox. Index DatetimeIndex (month start). attrs: {"source_id"}.
```

## 2. Crop knowledge base — `rotacast/knowledge/crops.yaml` + `crops.py`

```yaml
- id: wheat_winter                 # snake_case, unique
  name: {en: Winter wheat, tr: Kışlık buğday}
  family: Poaceae                  # botanical family (pest/disease break logic)
  category: cereal                 # cereal | legume | oilseed | root | forage | cover | fiber
  season: winter                   # winter (autumn-sown) | spring | summer
  sowing:                          # climate-driven sowing rule, applied to each year's weather
    rule: tmean_below              # tmean_below (autumn sowing) | tmean_above (spring/summer sowing)
    threshold_c: 12                # 7-day rolling mean temperature threshold
    window_doy: [270, 330]         # earliest/latest DOY in which the rule is searched (N. hemisphere)
  t_base_c: 0                      # GDD base temperature
  gdd_to_maturity: 2100            # °C·day from sowing to maturity
  heat_stress_tmax_c: 32           # Tmax above this during sensitive stage = heat-stress day
  frost_damage_tmin_c: -2          # Tmin below this during sensitive stage = frost-damage day
  sensitive_stage: mid             # FAO-56 stage where heat/frost hurts yield most
  fao56:
    stage_days: [160, 75, 40, 30]  # L_ini, L_dev, L_mid, L_late (FAO-56 Table 11)
    kc: [0.7, 1.15, 0.3]           # Kc_ini, Kc_mid, Kc_end (FAO-56 Table 12)
    root_depth_m: [0.3, 1.5]       # Zr min/max
    p: 0.55                        # depletion fraction (FAO-56 Table 22)
    ky: 1.05                       # seasonal yield response factor (FAO-33 / FAO-66)
  drought_tolerance: 3             # 1 (low) – 5 (high)
  n_fixation_kg_ha: 0              # typical net N left for next crop
  residue_index: 0.7               # 0–1 relative organic-matter return
  rusle_c: 0.25                    # seasonal average cover-management factor
  root_type: fibrous               # fibrous | tap | deep_tap
  forage_value: 1                  # 0–3
  disease_groups: [cereal_root_rots, cereal_rusts]
  economics:                       # Konya/Türkiye context; values documented in sources
    yield_t_ha: {rainfed: 2.5, irrigated: 5.5}
    price_usd_t: 280
  irrigation_typical: optional     # none | optional | required
  notes: {en: "...", tr: "..."}
  sources: [fao56_tables, ecocrop, ...]   # ids from docs/SOURCES.md
```

```python
# crops.py
@dataclass(frozen=True)
class Crop: ...                 # typed mirror of the YAML (nested dataclasses ok)
def load_crops(path: Path | None = None) -> dict[str, Crop]: ...   # validates; raises ValueError naming the bad field
```

Season length: the stage_days sum is the reference; the engine stretches/compresses stages proportionally to match `gdd_to_maturity` in each year's weather (capped to ±30%).

## 3. Engine — `rotacast/engine/`

```python
# climate.py
def et0_penman_monteith(df: pd.DataFrame, lat: float, elevation_m: float) -> pd.Series: ...
# FAO-56 eq. 6 daily reference ET (mm/day) from tmax, tmin, rh, wind2m, rs. Named "et0".
def add_et0(df, lat, elevation_m) -> pd.DataFrame: ...                 # returns copy with "et0" column
def climate_profile(df: pd.DataFrame, lat: float) -> dict: ...
# Returns the "climate" object of the FieldReport (section 4).

# phenology.py
def analyze_ndvi(ndvi: pd.DataFrame) -> dict: ...
# Returns the "field_memory" object of the FieldReport. Filters reliability>1, Savitzky–Golay smoothing,
# per-year green-up / peak / senescence DOY, bare-soil probability per DOY, bare windows, anomaly z-scores,
# stress years, inferred pattern per year: "winter_crop" | "summer_crop" | "double_crop" | "fallow".

# waterbalance.py   (FAO-56 single crop coefficient, daily root-zone depletion, chapters 6 & 8)
@dataclass
class SeasonResult:
    crop_id: str; sow_date: date; harvest_date: date
    etc_mm: float; eta_mm: float; precip_mm: float; effective_precip_mm: float
    irrigation_mm: float; drainage_mm: float
    stress_days: int               # days with Ks < 1
    yield_ratio: float             # Ya/Ym from Ky (1 - Ky(1 - ETa/ETc)), clipped 0..1
    heat_days: int; frost_days: int  # in the sensitive stage
    soil_cover_days: int           # days with canopy cover > 30 % (Kc-based proxy)
def simulate_season(crop: Crop, sow_date: date, weather: pd.DataFrame, soil: SoilProfile,
                    irrigation: str = "none", initial_depletion_frac: float = 0.3) -> SeasonResult: ...
# weather must contain precip and et0. irrigation: "none" | "deficit" (refill to 50 % of RAW when Dr > 1.5·RAW)
# | "full" (refill to field capacity when Dr > RAW).

# rotations.py
@dataclass
class RotationStep:
    crop_id: str; year: int        # 1-based year within the rotation cycle
    irrigation: str = "none"
@dataclass
class Rotation:
    id: str; name: dict; archetype: str   # baseline | water_saver | soil_builder | balanced_income
    steps: list[RotationStep]
def simulate_rotation(rotation: Rotation, weather: pd.DataFrame, soil: SoilProfile, crops: dict[str, Crop],
                      start_years: list[int]) -> dict: ...
# Runs the cycle once per historical start year (ensemble), carrying soil water between seasons,
# finding sowing dates from each crop's sowing rule. Returns indicators with p10/p50/p90 (section 4).
def generate_candidates(crops, climate: dict, field_memory: dict, constraints: dict) -> list[Rotation]: ...
def pick_strategies(results: list[dict], priorities: dict) -> list[dict]: ...
# Pareto front over indicators, then one strategy per non-baseline archetype, maximally different.

# scoring.py
DEFAULT_PRIORITIES = {"water": 0.3, "soil": 0.25, "income": 0.25, "erosion": 0.1, "risk": 0.1}
def score(indicators: dict, baseline: dict, priorities: dict) -> dict: ...  # {"score": float 0–100, "breakdown": {...}}

# regional.py  (later)  — basin grid sampling, aggregation, GRACE comparison, production projection
```

## 4. FieldReport JSON — API response of `POST /api/field/analyze`

Request:
```json
{"lat": 37.60, "lon": 32.75,
 "current_rotation": [{"crop_id": "wheat_winter", "irrigation": "none"},
                      {"crop_id": "sugar_beet", "irrigation": "full"},
                      {"crop_id": "maize_grain", "irrigation": "full"}],
 "constraints": {"water_access": "limited", "max_irrigated_share": 0.5},
 "priorities": {"water": 0.3, "soil": 0.25, "income": 0.25, "erosion": 0.1, "risk": 0.1},
 "scenario": {"delta_t_c": 0, "precip_change_pct": 0},
 "lang": "tr"}
```

Response (all numbers are plain floats; `{p10,p50,p90}` objects where marked *band*):
```jsonc
{
  "location": {"lat": 37.6, "lon": 32.75, "elevation_m": 1010, "label": "Çumra, Konya"},
  "sources": [{"id": "nasa_power", "name": "NASA POWER", "detail": "Daily, 0.5°×0.625°", "url": "..."}],
  "climate": {
    "period": [1991, 2025],
    "annual": [{"year": 1991, "precip_mm": 0, "et0_mm": 0, "tmean_c": 0, "gdd0": 0, "heat_days_35": 0, "frost_days": 0}],
    "monthly_normals": [{"month": 1, "precip_mm": 0, "et0_mm": 0, "tmean_c": 0, "tmin_c": 0, "tmax_c": 0}],
    "frost": {"last_spring_doy": {"p10":0,"p50":0,"p90":0}, "first_fall_doy": {"p10":0,"p50":0,"p90":0},
              "frost_free_days": {"p10":0,"p50":0,"p90":0}},
    "water_balance": {"aridity_index": 0, "annual_deficit_mm": 0},     // P/ET0, ET0-P
    "shift": {"early": [1991, 2005], "late": [2011, 2025],
              "metrics": [{"id": "last_spring_frost", "label": {"en": "...", "tr": "..."}, "unit": "doy",
                           "early": 0, "late": 0, "delta": 0, "trend_per_decade": 0, "p_value": 0}]}
  },
  "field_memory": {
    "ndvi": [{"date": "2000-02-18", "ndvi": 0.21, "ndvi_smooth": 0.2}],
    "years": [{"year": 2001, "greenup_doy": 0, "peak_doy": 0, "peak_ndvi": 0, "senescence_doy": 0,
               "season_integral": 0, "anomaly_z": 0, "stress": false, "pattern": "winter_crop"}],
    "bare_probability": [{"doy": 1, "p_bare": 0.0}],
    "bare_windows": [{"start_doy": 190, "end_doy": 290, "probability": 0.8}],
    "stress_years": [2008, 2014, 2021]
  },
  "soil": {"clay_pct": 0, "sand_pct": 0, "silt_pct": 0, "soc_gkg": 0, "ph": 0, "texture_class": "clay loam",
           "taw_mm_per_m": 0, "source_id": "soilgrids"},
  "terrain": {"elevation_m": 0, "slope_pct": 0},
  "strategies": [{
    "id": "baseline", "archetype": "baseline", "name": {"en": "Current rotation", "tr": "Mevcut rotasyon"},
    "cycle_years": 3,
    "calendar": [{"year": 1, "crop_id": "wheat_winter", "crop_name": {"en":"","tr":""}, "irrigation": "none",
                  "sow": "10-15", "harvest": "07-05", "kind": "main"}],      // kind: main | cover
    "indicators": {
      "irrigation_mm_yr": {"p10":0,"p50":0,"p90":0},             // band
      "water_m3_ha_yr": {"p10":0,"p50":0,"p90":0},               // band
      "yield_ratio": {"p10":0,"p50":0,"p90":0},                  // band, mean over cycle
      "stress_days_yr": {"p10":0,"p50":0,"p90":0},               // band
      "frost_risk": 0, "heat_risk": 0,                           // probability 0–1 a crop in the cycle is hit
      "n_balance_kg_ha_yr": 0, "residue_index": 0, "soil_cover_days_yr": 0,
      "erosion_rel": 0,                                          // relative to baseline = 1.0
      "pest_break": 0,                                           // 0–1
      "income_usd_ha_yr": {"p10":0,"p50":0,"p90":0}             // band
    },
    "score": 0, "score_breakdown": {"water": 0, "soil": 0, "income": 0, "erosion": 0, "risk": 0},
    "evidence": {
      "why": [{"text": {"en":"","tr":""}, "facts": ["f12"]}],
      "benefits": [{"text": {"en":"","tr":""}, "facts": ["f3"]}],
      "gaps": [{"text": {"en":"","tr":""}}],
      "risks": [{"text": {"en":"","tr":""}, "check_with": "agronomist"}]
    }
  }],
  "facts": [{"id": "f12", "text": {"en":"","tr":""}, "value": 0, "unit": "mm", "source_id": "nasa_power"}],
  "disclaimer": {"en": "...", "tr": "..."}
}
```

`facts` is the single source of numbers for any narrative text (the SI layer may only reference fact ids).

Clarifications (v1.1):
- `score` and every `score_breakdown` value are on a 0–100 scale; the baseline scores 50 on every axis.
- `calendar[].year` is the cycle year in which the crop is **harvested**. A `sow` date later in the year than `harvest` means the crop was sown in the autumn of the previous cycle year (winter crops). Cover crops are separate entries with `kind: "cover"` and the `year` of the main crop they follow.
- `risks[].check_with` enum: `agronomist` | `extension_service` | `market`.
- `location.label` is always a non-empty string (falls back to formatted coordinates).
- **Zone cards (v1.2, METHODS §7.1).** For a point inside a Konya zone the strategies are
  `baseline, balanced_transition, low_risk, innovative` (a card is left out when it cannot be built; the reason is in
  `cards.notes`). Outside a zone the old `water_saver, soil_builder, balanced_income` archetypes are returned; the
  basin report always uses them. Extra keys:
  ```jsonc
  "cards": {"zone": "central", "notes": {"low_risk": "no_candidate_within_limits" | "...", "balanced_transition": "no_verified_specialty",
            "innovative": "no_local_evidence"}, "allowed_crops": [""], "caution_crops": [""],
            "limits": {"water_m3_ha_yr_max": 0, "erosion_rel_max": 1.0}},
  // per card strategy:
  "coverage": 0.75,                       // share of the field the numbers cover (< 1 when a specialty crop is not modelled)
  "parts": [{"share": 0.75, "kind": "rotation", "role": "verified_rotation|current_rotation", "rotation_id": "",
             "rotation_name": {"en": "", "tr": ""}, "modeled": true},
            {"share": 0.25, "kind": "specialty", "modeled": false, "share_range": [0.2, 0.3],
             "crop": {/* whitelist record + engine_ids, modeled */} | null, "options": [/* unmodelled specialty crops */]}],
  "trials": [{"crop": {}, "share_range": [0.05, 0.1], "modeled": true,
              "water_m3_ha_yr": {"p10": 0, "p50": 0, "p90": 0}, "income_usd_ha_yr": {}}]   // innovative card only
  ```
- `field_memory.bare_probability` is reported per 16-day composite bin (`doy` = bin start); `bare_windows` that wrap the new year may appear as two windows (end of year and start of year).


---

## 5. BasinReport JSON — `data/demo/basin_report_konya.json`

Produced by `backend/scripts/build_basin_report.py` (`rotacast/regional.py`). Scenario analysis, **not a forecast**. Strict JSON (no NaN). All shown labels are bilingual `{en, tr}`. Units: area ha / km2, water Mm3/yr (million m3 per year) or m3/ha, production t/yr.

```jsonc
{
  "schema_version": "1.1", "generated": "2026-11-12",
  "scenario_notice": {"en": "", "tr": ""},
  "region": {"id": "konya_closed_basin", "name": {"en":"","tr":""}, "bbox": [32.0, 37.0, 34.5, 38.8],   // min_lon,min_lat,max_lon,max_lat
             "bbox_area_km2": 0, "approximation": "bounding box + MODIS cropland filter"},
  "totals": {"n_cells": 0, "cropland_ha": 0, "irrigated_ha": 0, "skipped_cells": [{"id": "", "reason": ""}]},
  "baseline": {"mix": [{"id": "wheat_beet_maize", "weight": 0.42,        // calibrated mix of representative irrigated rotations, weights sum to 1
                        "rotation": [{"crop_id": "wheat_winter", "irrigation": "deficit"}]}],
               "target_noncereal_shares": {"sugar_beet": 0.25},         // Konya statistics (see assumptions[id=baseline_mix])
               "achieved_noncereal_shares": {"sugar_beet": 0.25}, "cereal_share_of_area": 0.43,
               "irrigated_ha": 0,
               "irrigation_demand_mm3_yr": {"p10": 0, "p50": 0, "p90": 0},   // whole-basin baseline demand
               "production_t_yr": [{"crop_id": "", "name": {"en":"","tr":""}, "t_yr": 0}]},
  "strategies": [{"id": "water_saver|soil_builder|balanced_income", "name": {"en":"","tr":""}}],
  "adoption_rates": [0.1, 0.3, 0.5],
  "horizons": [5, 10],                       // years; 10 = "trend continuation" climate (see assumptions)
  "cells": [{                                // one per POWER grid cell with cropland fraction > threshold
    "id": "c+37.50_+032.500", "lat": 0, "lon": 0,
    "bounds": [lon0, lat0, lon1, lat1],      // full POWER cell
    "clip": [lon0, lat0, lon1, lat1],        // cell ∩ bbox (area_km2 refers to this)
    "area_km2": 0, "cropland_fraction": 0, "cropland_ha": 0, "irrigated_ha": 0,
    "elevation_m": 0, "soil_source": "soilgrids|soil_default", "delta_t_c_per_decade": 0,
    "precip_correction": {"applied": true, "source_id": "gpm_imerg|chirps", "factors_by_month": {"1": 1.0},
                          "power_mean_mm": 0, "sat_mean_mm": 0}, // applied=false -> {"reason": ""}
    "baseline_water_m3_ha": 0,               // p50 of the weight-averaged baseline mix
    "baseline_water_m3_ha_band": {"p10":0,"p50":0,"p90":0}, "baseline_crop_t_ha_yr": {"<crop_id>": 0},
    "reference_baseline": "wheat_beet_maize", // mix rotation the archetype scores are relative to
    "best_strategy": {"archetype": "water_saver",     // null if no archetype was found "name": {"en":"","tr":""}, "score": 0},   // highest score among the 3 archetypes (map colour)
    "strategies": {"<archetype>": {
        "score": 50, "rotation_name": {"en":"","tr":""}, "steps": [{"crop_id":"","year":1,"irrigation":"none"}],
        "water_m3_ha": {"p10":0,"p50":0,"p90":0}, "water_change_m3_ha_p50": 0,   // vs. the baseline mix; negative = less water
        "crop_t_ha_yr": {"<crop_id>": 0}}}    // t/ha per rotation-year, current climate
  }],
  "scenarios": {                              // [archetype][adoption rate as string][horizon years as string]
    "water_saver": {"0.3": {"10": {
      "climate": "current|trend_continuation",
      "irrigation_change_mm3_yr": {"p10": 0, "p50": 0, "p90": 0},   // negative = water saved; p10<=p50<=p90 (sorted values)
      "grace_offset_pct": {"p10": 0, "p50": 0, "p90": 0},           // share of the GRACE storage loss offset; null if GRACE unavailable
      "production_change_t_yr": [{"crop_id": "", "name": {"en":"","tr":""}, "change_t_yr": 0, "baseline_t_yr": 0}]   // sorted by |change|; baseline_t_yr = whole-basin baseline production of the crop
    }}}
  },
  "grace": {
    "available": true, "source_id": "grace_csr_mascon", "bbox": [], "area_km2": 0,
    "period": ["2002-04-01", "2025-12-01"], "n_months": 0,
    "trend_cm_yr": 0, "trend_ci95_cm_yr": [0, 0],      // OLS, AR(1)-adjusted CI
    "volume_change_mm3_yr": 0, "volume_change_ci95_mm3_yr": [0, 0],   // trend x bbox area; negative = storage loss
    "loss_mm3_yr": 0,                                  // positive loss used as the denominator; null if not a loss
    "series": [{"date": "2003-01-01", "tws_cm": 0}], "note": {"en":"","tr":""}
    // available=false -> trend/volume/series are null/[] and note explains why
  },
  "assumptions": [{"id": "", "label": {"en":"","tr":""}, "value": "any", "source": ""}],
  "limitations": [{"en": "", "tr": ""}],
  "sources": [{"id": "", "name": "", "url": ""}]
}
```

Notes: the baseline is a weighted mix of representative irrigated rotations calibrated to Konya crop-area statistics. A fraction of the *irrigated* area of every cell (irrigated = cropland × `irrigated_share`), taken proportionally from each baseline rotation, moves to the cell's own archetype rotation, so a crop can lose at most its baseline area share. `assumptions[id=plausibility_irrigation]` compares the modelled baseline demand with published basin irrigation figures. Results are steady-state annual rates at the horizon (no ramp-up). The p10/p50/p90 water band sums same-quantile differences across cells (weather assumed perfectly correlated).

---

## 6. Field request/report extensions (v1.2, Başlangıç / Gelişmiş modes)

All additions are **optional**. A request without them must give exactly the v1.1 report (same keys, same numbers):
new response keys appear **only** when the matching input was sent.

### 6.1 Request additions (`POST /api/field/analyze`)

```jsonc
{
  // ...v1.1 fields unchanged...
  "field_polygon": {"type": "Polygon", "coordinates": [[[32.749, 37.599], [32.751, 37.599], [32.751, 37.601], [32.749, 37.601], [32.749, 37.599]]]},
  //   GeoJSON Polygon, WGS84 [lon, lat], one outer ring (holes ignored). Ring may be open or closed; >= 3 distinct
  //   vertices; must not self-intersect; area 0.01–10 000 ha. When present, lat/lon are replaced by the polygon centroid.
  "field_details": {
    "soil": {"texture_class": "clay loam", "clay_pct": 38, "sand_pct": 22, "soc_gkg": 9, "ph": 7.9},
    //   every key optional. texture_class: one of the 12 USDA class names (lower case, as SoilProfile.texture_class).
    //   clay_pct, sand_pct 0–100 and clay+sand <= 100; soc_gkg 0–200; ph 3–10.
    "excluded_crops": ["sugar_beet", {"crop_id": "potato", "reason": "no_buyer"}],
    //   plain id or object; reason: no_equipment | no_buyer | not_wanted (default not_wanted)
    "irrigation_method": "drip",            // flood | furrow | sprinkler | drip
    "water_quota_m3_yr": 40000,             // >= 0. Field total if the polygon area is known, else m³/ha/yr
    "yields_t_ha": {"wheat_winter": 4.2},   // > 0 and <= 200, known crop ids
    "history": [{"year": 2024, "crop_id": "maize_grain"}],   // year 2000..last year, known crop ids, unique years
    "irrigation_applied_m3_ha": {"maize_grain": 6500}       // >= 0 and <= 30 000, known crop ids
  }
}
```

Invalid values (out of range, clay+sand > 100, unknown crop id, unknown enum, self-intersecting polygon) → **422**
with FastAPI's standard body `{"detail": [{"loc": ["body", "field_details", "water_quota_m3_yr"], "msg": "...", "type": "..."}]}`
so the UI can show the message next to the field. `null`, `{}` and `[]` values mean "not given".

### 6.2 Effects

| Input | Effect |
|---|---|
| `field_polygon` | lat/lon = centroid; `location.area_ha`, `location.polygon`; extra `evidence.gaps` item (MODIS 250 m pixel does not resolve the polygon yet) |
| `soil` | Overrides the SoilGrids values that were given; silt = 100 − clay − sand; texture class recomputed from clay/sand unless given; if only `texture_class` is given, representative clay/sand of that class are used for the hydraulics; fc, wp, `taw_mm_per_m` recomputed (Saxton & Rawls 2006). `soil.source_id = "user"` |
| `excluded_crops` | Removed from generated candidates (`constraints.exclude_crops`). The user's own current rotation is not changed. Each non-baseline strategy gets a `why` item (appended after the first three) naming the excluded crops and reasons |
| `irrigation_method` | Gross water = net irrigation / efficiency (flood 0.55, furrow 0.65, sprinkler 0.75, drip 0.90; `docs/METHODS.md`, `docs/SOURCES.md` id `irrigation_efficiency`). `water_m3_ha_yr` and the water cost in income are gross; `irrigation_mm_yr` stays net crop irrigation |
| `water_quota_m3_yr` | Per-ha quota = quota / `area_ha` (or the value itself without area). Candidate generation uses `water_access: "full"` (quota 0 → `"none"`) instead of the request's `water_access`. Candidates whose p50 `water_m3_ha_yr` exceed the per-ha quota are dropped before picking; if fewer than 3 candidates remain, the over-quota ones stay eligible but are marked. Baseline over quota → a `risks` item on the baseline (`check_with: "extension_service"`) |
| `yields_t_ha` | Per crop, factor = declared / regional reference (`economics.yield_t_ha.irrigated` if that crop is irrigated in the current rotation, else `rainfed`); the crop's potential yield used in income is multiplied by the factor in every strategy |
| `history` | Compared with `field_memory.years[].pattern` (winter-season crop → `winter_crop`, spring/summer crop → `summer_crop`, a `double_crop` year agrees with either). Model unchanged |
| `irrigation_applied_m3_ha` | Compared with the modelled per-crop gross irrigation of the current rotation. Model unchanged |

Every user value that is used becomes a fact with `source_id: "user"`; `sources` then includes
`{"id": "user", "name": "User-provided field data / Kullanıcı beyanı", ...}`.

### 6.3 Response additions

```jsonc
{
  "location": {"...": "...", "area_ha": 4.83, "polygon": {"type": "Polygon", "coordinates": [[[0, 0]]]}},  // only with field_polygon
  "user_inputs": [   // only when field_polygon or any field_details value was given; order = UI order
    {"id": "soil",   // polygon | soil | excluded_crops | irrigation_method | water_quota | yields | history | irrigation_applied
     "label": {"en": "Soil", "tr": "Toprak"},
     "value": {"en": "clay loam, clay 38 %, sand 22 %", "tr": "killi tın, kil %38, kum %22"},   // what you entered
     "model": {"en": "SoilGrids: loam, clay 24 %", "tr": "SoilGrids: tın, kil %24"},            // satellite/model estimate it replaces or is compared to; null if none
     "fact": "f31"}
  ],
  "irrigation": {"method": "drip", "efficiency": 0.9, "source_id": "irrigation_efficiency"},   // only with irrigation_method
  "quota": {"quota_m3_yr": 40000, "quota_m3_ha_yr": 8281.6, "basis": "field_total",           // basis: field_total | per_ha
            "baseline_exceeds": false, "n_candidates_excluded": 12, "relaxed": false},          // only with water_quota_m3_yr; relaxed: < 3 options fit, so over-quota ones were kept (marked)
  "strategies": [{"...": "...", "exceeds_quota": false}],                                       // key only with water_quota_m3_yr
  "yield_check": [{"crop_id": "wheat_winter", "declared_t_ha": 4.2, "regional_t_ha": 5.5, "factor": 0.764}],
  "history_check": {"n_years": 3, "n_agree": 2, "agreement": 0.667,   // agreement null when n_years is 0
                    "years": [{"year": 2024, "crop_id": "maize_grain", "declared_pattern": "summer_crop",
                               "satellite_pattern": "summer_crop", "agree": true}]},   // years without satellite data: satellite_pattern null, agree null, not counted
  "irrigation_check": [{"crop_id": "maize_grain", "declared_m3_ha": 6500, "modelled_m3_ha": 7120, "diff_pct": -8.7}]
  //   modelled = mean gross m³/ha of that crop's season(s) in the current rotation; crops not in the rotation: modelled null
}
```

Field totals are not sent by the API; the UI multiplies per-ha values by `location.area_ha`.

---

## 7. Konya zones — `GET /api/zones` and `FieldReport.zone`

Files: `data/zones/konya_zones.geojson`, `konya_boundary.geojson`, `konya_lakes.geojson`, `konya_districts.geojson`
(built by `backend/scripts/build_konya_zones.py`; method in METHODS.md §10).

```jsonc
// GET /api/zones
{
  "zones": {"type": "FeatureCollection", "meta": {"built": "", "method": "", "rules": {}, "sources": {}},
    "features": [{"type": "Feature", "geometry": {},          // Polygon | MultiPolygon, lakes cut out
      "properties": {
        "id": 1, "key": "toros", "color": "#4E79A7", "name_tr": "", "name_en": "", "desc_tr": "", "desc_en": "",
        "area_km2": 0, "districts": [{"name": "", "share": 0.0}],      // share of the zone's area, >= 1 %
        "elevation_m": {"p10": 0, "p50": 0, "p90": 0},
        "stations": [{
          "station": "HADIM", "name": "Hadim", "period": "1991-2020", "url": "", "lat": 0, "lon": 0,
          "aydeniz": {"index": 0, "type": ""}, "erinc": {"index": 0, "type": ""}, "de_martonne": {"index": 0, "type": ""},
          "trewartha_winter": {"type": "", "mean_temp_c": 0}, "trewartha_summer": {"type": "", "mean_temp_c": 0},
          "thornthwaite": {"class": "", "explanation": ""},
          "nasa_power": {"period": "2001-2025", "grid": "", "t2m_mean_c": 0, "frost_days_yr": 0, "spring_frost_days": 0,
                         "autumn_frost_days": 0, "hottest_month_mean_c": 0, "coldest_month_mean_c": 0, "rh2m_pct": 0}}]}}]},
  "boundary": {"type": "FeatureCollection", "features": [/* Konya province */]},
  "lakes": {"type": "FeatureCollection", "features": [/* properties.name */]}
}

// POST /api/field/analyze adds:
"zone": {"id": 5, "key": "central", "color": "", "name": {"tr": "", "en": ""}, "desc": {"tr": "", "en": ""},
         "elevation_m": {"p10": 0, "p50": 0, "p90": 0}, "field_elevation_m": 0,
         "elevation_position": "low|mid|high",   // vs. the zone band; null if the field elevation is unknown
         "stations": [/* as above */],
         "crops": {                              // data/zones/zone_crops.json (METHODS §10.1); null if the file is missing
           "version": "2026-11-14", "caveat": {"tr": "", "en": ""}, "groups": {"field": {"tr": "", "en": ""}},
           "crops": [{"name": {"tr": "", "en": ""}, "status": "verified|pilot",
                      "group": "field|special|protected|method|tech", "caution"?: true, "districts"?: [""],
                      "note"?: {"tr": "", "en": ""}, "sources": ["ilt_aromatik"], "engine"?: ["wheat_winter"]}],
           "notes": [{"tr": "", "en": "", "sources": [""]}],
           "sources": [{"id": "", "title": "", "url": "" /* or null */}]}}  // excluded crops are never returned
// Points outside Konya or on a lake: HTTP 422, detail = {"code": "outside_konya" | "on_lake", "message": "", "lake"?: ""}
// (detail is an object here; validation errors of section 6.1 have a list detail). With field_polygon, the centroid is checked.
```
