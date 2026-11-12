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
