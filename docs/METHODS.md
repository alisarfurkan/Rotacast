# Rotacast methods

This document describes what the code in `backend/rotacast/` actually does. Every dataset has an id that is
defined, with citation and license, in [SOURCES.md](SOURCES.md). Data shapes are in [CONTRACTS.md](CONTRACTS.md).

Rotacast has two levels:

1. **Field analysis** (`report.py`): one point (lat/lon) -> climate shift, NDVI Field Memory, simulated
   rotations, three recommended strategies against the current rotation.
2. **Basin View** (`regional.py`): the same engine run on a grid of cells over the Konya Closed Basin and scaled to
   the basin as an explicit *scenario*, compared with the GRACE water-storage trend.

## 1. Data sources and resolutions

| Input | Source id | Resolution | Used for |
|---|---|---|---|
| Daily weather (Tmax, Tmin, T, rain, RH, wind, solar, soil wetness), 1991 to last full year | `nasa_power` | 0.5 x 0.625 deg (MERRA-2), daily | Climate, ET0, water balance |
| Satellite rain | `chirps` (preferred), `gpm_imerg` (fallback), via SERVIR ClimateSERV | 0.05 deg / 0.1 deg, daily | Bias correction of POWER rain |
| NDVI 2000-02 onward | `modis_mod13q1` | 250 m, 16-day | Field Memory (phenology, bare windows, stress years) |
| Land cover | `modis_mcd12q1` | 500 m, yearly | Cropland area per basin cell |
| Soil texture, SOC, pH, bulk density (0-30 cm) | `soilgrids` (fallback `soil_default`) | 250 m | Water holding capacity |
| Elevation, slope | `srtm_terrain_tiles` | ~30 m tiles | ET0 pressure term, slope |
| Total water storage anomaly | `grace_csr_mascon` | 0.25 deg mascons, monthly | Basin comparison |
| Crop parameters, yields, prices | `fao56`, `fao33`, `fao66`, `ecocrop`, `faostat`, `tuik`, `tmo`, `rusle_ah703`, `peoples2009` -> `knowledge/crops.yaml` (21 crops) | n/a | Crop model, economics |
| Konya crop areas 2024, irrigated land | `tuik`, `konya_irrigated_share` | province | Basin baseline calibration |

All connectors cache responses to `data/cache/`; with `ROTACAST_OFFLINE=1` they never touch the network and raise a
cache miss instead.

## 2. Precipitation bias correction

NASA POWER rain is a 0.5 x 0.625 deg reanalysis product and is too wet on dry plains (at Cumra, Konya: POWER 533 mm/yr
vs CHIRPS 302 mm/yr). Because crop water stress and irrigation demand are driven by rain, Rotacast corrects it
(`connectors/precip.py: bias_correct_power`).

For each calendar month *m*, over the complete months where POWER and the satellite series overlap:

```
f_m = clip( sum(P_sat, month m) / sum(P_power, month m) , 0.3 , 1.5 )
P_corrected(day d) = f_month(d) * P_power(d)
```

- The factor keeps POWER's day-to-day timing and rescales its monthly totals, so ET0, temperature and radiation are untouched.
- Requires at least 8 overlapping years; otherwise the correction is not applied and the report says so.
- The ratio is clipped to [0.3, 1.5] to stop one very dry/wet month from producing an absurd multiplier.
- **CHIRPS is preferred** (`PREFERENCE = (chirps, gpm_imerg)`): it is gauge-blended and goes back to 1981; GPM IMERG
  produced spurious 100-230 mm days on the Konya plain, so it is only a fallback.
- The applied factors, source, and POWER/satellite annual means are returned in the report (`precip_correction`).
- If the satellite service fails the field report degrades gracefully to raw POWER rain and states that in its "gaps".
- The basin run uses a shorter satellite window (from 2013) to keep ClimateSERV calls modest.

## 3. ET0 and water balance (FAO-56)

**Reference evapotranspiration** (`engine/climate.py`): FAO-56 Penman-Monteith, daily, G = 0:

```
ET0 = [0.408 * D * (Rn - G) + gamma * 900/(T+273) * u2 * (es - ea)] / [D + gamma * (1 + 0.34 * u2)]
```

with extraterrestrial radiation from latitude and day of year (FAO-56 eq. 21-25), Rs from POWER, humidity from
POWER RH, and pressure from elevation.

**Crop water balance** (`engine/waterbalance.py`): a daily single-crop-coefficient root-zone model, vectorised over an
ensemble of sowing years.

- Sowing date: first day in the crop's window on which the 7-day mean temperature passes the crop's threshold.
- Season length: stages are scaled so the season ends when the crop's growing degree days (`gdd_to_maturity`) are reached in that year's weather, capped at +/-30 % of the reference stage lengths.
- Crop coefficient `Kc` is piecewise (constant initial, linear development and late stages). Root depth grows linearly.
- Depletion fraction `p` is ETc-adjusted (`p = p_table + 0.04 (5 - ETc)`, clipped 0.1-0.8); stress `Ks` follows FAO-56 eq. 84; `ETa = Ks * Kc * ET0`.
- Effective rain = rain minus USDA-SCS curve-number runoff (CN 75); capillary rise is 0; irrigation is a net depth at 100 % efficiency.
- Irrigation modes: `none`, `deficit` (refill to 50 % of RAW when depletion exceeds 1.5 RAW), `full` (refill to field capacity when depletion exceeds RAW).
- Field capacity and wilting point come from soil texture and organic matter (Saxton & Rawls 2006).
- Between crops a bare-soil bucket (1 m, `Kc_bare` 0.15-0.30) carries soil water over, so one crop's use affects the next.
- **Yield**: FAO-33 linear response `1 - Ya/Ym = Ky * (1 - ETa/ETc)`, multiplied by a heuristic heat/frost penalty (3 % per damage day in the sensitive stage, capped at 40 %). `Ym` is the water-unlimited potential yield from `crops.yaml`.

## 4. Climate shift

`climate_profile` computes, from the daily series, the annual precipitation, ET0, mean temperature, growing degree
days, days with Tmax >= 35 degC, frost days (Tmin <= 0 degC), frost-free days, last spring / first fall frost, and
monthly normals with p10/p50/p90 spread.

The **shift** compares the first and last 15 full years of the record (e.g. 1991-2005 vs 2010-2024) for each metric
(`late - early`), and reports a **Sen slope** per decade with a two-sided **Mann-Kendall** p-value on the full record.
Nothing is projected from climate models. Optional what-if inputs (`scenario.delta_t_c`, `precip_change_pct`) shift
the observed weather before simulation and recompute ET0.

## 5. NDVI Field Memory and phenology

`engine/phenology.py` turns 25 years of MOD13Q1 NDVI into a field's own cropping history:

1. Drop low-quality pixels (reliability > 1), place observations on the 16-day grid, interpolate gaps linearly.
2. Smooth with a Savitzky-Golay filter (window 5, order 2).
3. Per calendar year (needs at least 20 of 23 composites): green-up and senescence are the dates the smoothed curve crosses *baseline + 20 % of amplitude* on the rising and falling limb (TIMESAT convention); also peak date and height.
4. **Pattern** per year: `fallow` (amplitude < 0.12), `winter_crop` (single peak before day 175), `summer_crop` (single peak after), `double_crop` (two well-separated, prominent peaks).
5. **Season integral** = sum of `max(NDVI - field baseline, 0) * 16 days`, using one field baseline (median annual minimum); `anomaly_z` is its z-score across years; a year is a **stress year** if z <= -1 (never for fallow years).
6. **Bare-soil windows**: a field-specific bare NDVI threshold = median annual minimum + 0.05, clipped to [0.15, 0.30]. The probability that each 16-day bin is bare is the share of years below it; runs of bins with p >= 0.6 become bare windows.

Field Memory is evidence shown to the farmer (what the satellite saw on *this* field). It does not feed the yield
model; bare windows for cover-crop placement use the crops' typical timing (`generate_candidates` takes
`field_memory` for interface symmetry only).

## 6. Rotation candidate generation

`generate_candidates` randomly (seeded, `seed=42`, capped at 300) enumerates 3-4 year sequences of main crops from the
21-crop knowledge base, subject to:

- crop passes a heuristic climate-suitability filter: spring/summer crops must fit the median frost-free period (+15 %), winter crops must survive the estimated winter minimum;
- perennials (alfalfa, sainfoin) are not generated (see Limitations);
- a crop appears at most once per cycle; no same botanical family or shared disease group in consecutive years (cyclic);
- every harvest leaves time for the next sowing window (+10 day gap);
- at least one legume per cycle when a suitable one exists;
- water constraints: `water_access` (none / limited / full) and `max_irrigated_share` bound the irrigated years; "required-irrigation" crops are dropped when access is none;
- optionally a cover crop is inserted into bare windows of 60+ days (sown after harvest + 10 d, terminated 7 d before the next sowing, skipped if under 45 days).

`simulate_rotation` runs each candidate (and the farmer's current rotation) once per **start year** (up to 20 historical
start years) carrying soil water between seasons. Start years where sowing windows do not fit are dropped; a
rotation is "feasible" if at least 70 % of start years work.

Indicators per rotation (cycle totals divided by cycle length): net irrigation (mm and m3/ha/yr), yield ratio, stress
days, frost / heat hit probability (>= 3 damage days in a season), N balance (crop N-credit table), residue index,
soil-cover days, relative erosion (RUSLE cover factor C x erosive days; bare soil C = 1), pest-break index, income.
`income = yield * price - 0.05 USD/m3 * irrigation` (plus cover-crop cost 40 USD/ha). With the optional irrigation method (section 11) the water in `water_m3_ha_yr` and in this cost is gross water.

## 7. Scoring and Pareto picking

Each of five dimensions gets a 0-100 sub-score relative to the current rotation, where the current rotation is exactly 50:

```
lower is better (water, erosion, risk):  s = 50 + 50 * clip((b - x) / max(b, eps), -1, 1)
higher is better (soil, income):         s = 50 + 50 * clip((x - b) / max(|b|, eps), -1, 1)
```

- *water* = p50 irrigation m3/ha/yr; *income* = p50 USD/ha/yr.
- *soil* = 0.4 N-balance term + 0.3 residue index + 0.3 share of the year with living cover.
- *risk* = 0.3 frost-hit + 0.3 heat-hit + 0.4 (1 - p10 yield ratio).

Total score = priority-weighted mean (defaults water 0.30, soil 0.25, income 0.25, erosion 0.10, risk 0.10; the user's
sliders re-weight). `pick_strategies` then finds the **Pareto front** over (water down, income up, soil up, erosion down,
risk down) and returns the baseline plus three **archetypes**, preferring distinct crop sets:

| Archetype | Rule |
|---|---|
| `water_saver` | minimum water among candidates keeping >= 60 % of baseline income |
| `soil_builder` | maximum soil composite |
| `balanced_income` | best priority-weighted score on the Pareto front, among candidates keeping >= 60 % of baseline income |

### 7.1 Zone cards (field page)

Inside a Konya zone the field page shows three cards built on the zone crop whitelist (§10.1) instead of the
archetypes above (`engine/cards.py`). The basin view (§9) keeps the archetypes, so its headline is unchanged.

- **Whitelist filter.** Generated candidates use only engine crops of `verified` field crops in the zone. Crops
  marked `caution` (real but not to be expanded: maize, sugar beet, alfalfa, potato in water-restricted zones) may
  appear only if they are already in the current rotation. Cover crops only if the species is verified (vetch).
- **Hard limits for every card.** p50 irrigation water ≤ the current rotation's, erosion ≤ the current rotation's.
  The user's priorities rank what passes; they cannot lift the limits. Candidates should also keep ≥ 60 % of the
  current income (soft: dropped if nothing passes).
- **Low risk and resilient:** whole field, lowest risk sub-score (frost, heat, low-yield years), ties by total score;
  first among candidates keeping ≥ 80 % of the current income (income risk), then ≥ 60 %.
- **Balanced transition (default card):** 75 % on the best-scoring candidate within the limits (or the current
  rotation if none passes) + 25 % on a `verified` specialty crop of the zone (shown range 20–30 %).
- **Innovative crop opportunity:** 80 % current rotation + 20 % specialty crop (range 10–30 %), preferring a
  different crop than the balanced card. Official `pilot` crops are listed as **trial rows (5–10 %)** with their own
  modelled water and income when the engine has the crop (none today: the sorghum pilots are unmapped, see §10.1); they never enter the card's numbers.
- **Split fields.** Card indicators are the area-weighted blend of the parts, percentile by percentile (an
  approximation). The specialty share is simulated as the same crop every year on its block.
- **No invention.** A specialty crop without sourced engine parameters is listed with its evidence and marked
  "not in the numbers yet"; the card's numbers then cover only the modelled share (`coverage`). When no card can be
  built the report says why (`cards.notes`) instead of filling it.
- Not modelled: investment, labour, buyer/processing, time to first harvest for perennials.

### 7.2 Water-only specialty crops (cumin, fenugreek)

For two specialty crops only the **water need** is modelled (`engine/specialty_water.py`, parameters in
`knowledge/specialty_water.yaml`, a source comment on every number). Income, yield ratio and frost/heat risk are
**not** computed: there is no verified farm-gate price, no Ky and no temperature threshold for them.

- **Engine.** The same FAO-56 daily balance (`waterbalance._season_core`: ET0, Ks, soil TAW of the field, root growth,
  curve-number effective rain) runs for every weather year with a **fixed calendar** (no GDD scaling): sowing 26 Feb
  (DOY 57), harvest 23 Jul for cumin (DOY 204) and 2 Aug for fenugreek (DOY 214). Calendar: Central Anatolia
  rain-fed trials 2013, Ankara-Gölbaşı 1125 m, best yield at the earliest sowing (Uğur & Kan 2016, Selçuk Tarım
  Bilimleri Dergisi 3(2):205-209; same journal 3(2):210-214 for fenugreek). Soil water at sowing comes from the bare-soil
  balance since 1 October.
- **Parameters.** Kc ini/mid/end 0.40/1.00/0.60 (cumin) and 0.60/1.00/0.75 (fenugreek), root depth 0.10–0.40 m and
  0.30–0.80 m, p 0.40 for both: Pereira, Mota, Raziei & Paredes 2024, Irrigation Science 42(6), Tables 7 and 8.
  Cumin stage lengths 24/40/31/19 days (Reyhani & Khashei Siuki 2015 lysimeter) scaled to the season; fenugreek has
  no stage source, so FAO-56 Table 11 lentil proportions 20/30/60/40 are used and marked approximate.
- **Outputs** (p10/p50/p90 across years): `etc_mm` (unstressed need, Σ Kc·ET0), `rainfed_eta_mm` (water met by rain
  and stored soil water), `irr_need_full_m3_ha` (net irrigation of a full-irrigation run; 1 mm = 10 m³/ha) and the
  rain-fed irrigation water of the documented practice (0).
- **On the cards.** When no fully modelled specialty fits, a specialty with a water model is picked by name (cumin,
  which has a documented yield, before fenugreek; the innovative card avoids the balanced card's crop). The card's
  `water_m3_ha_yr` is the area blend of the field part and 0 for the rain-fed specialty, so it covers the **whole
  field** (`water_coverage` 1.0); every other indicator and the score inputs stay those of the field part
  (`coverage` = 1 − share). The part is marked `modeled: false`, `water_modeled: true` with its `water` bands. Hard
  limits apply to the blended water.
- **Limits.** Rain-fed ETa is limited by the shallow root zone (no capillary rise, roots to 0.4 m), so the rain-fed
  water use is a lower bound of what the crop gets in deeper soils; the stage lengths of fenugreek are approximate;
  the calendar is one Central Anatolian site applied to every Konya zone. Coriander, black cumin and fennel (no local
  calendar) and anise (no Kc) remain unmodelled.

## 8. Uncertainty bands

The p10 / p50 / p90 shown for water, income, yield ratio and stress days are percentiles across the **ensemble of
historical start years** (up to 20 sequences begun in different years of 1991 to last year, each simulated on its own
real weather). They therefore capture weather variability, not model, price or parameter uncertainty.

## 9. Basin scaling (Konya Closed Basin)

`regional.py` produces a scenario, not a forecast. Every assumption is a field of `BasinParams` and is echoed in the
report's `assumptions` list.

1. **Cells.** NASA POWER grid cells (0.5 x 0.625 deg) overlapping the bounding box 32.0-34.5 E, 37.0-38.8 N (cells with under 5 % overlap are dropped; 19 cells in the current report).
2. **Cropland area.** For each cell, MODIS MCD12Q1 (2022) pixels are sampled in four sub-windows; IGBP class 12 (cropland) counts 1.0, class 14 (mosaic) counts 0.5. Cells below 15 % cropland are dropped. Area uses the bounding-box-clipped cell on a sphere.
3. **Irrigated share.** `828,948 ha irrigated / 1,859,079 ha agricultural area = 0.446` (provincial figures quoted in the 2026 Konya Tarimi book). This includes irrigated orchards so it is an upper-ish estimate for field crops; irrigated ha per cell = cropland ha x 0.446.
4. **Calibrated baseline mix.** The baseline is a weighted mix of four representative irrigated rotations (wheat-maize, wheat-beet-maize, barley-sunflower-wheat, wheat-potato-bean). Weights are solved by constrained least squares (SLSQP) so that the *non-cereal* crop-area shares (grain+silage maize, sugar beet, sunflower x 0.3 irrigated, potato, dry bean) match **Konya province sown area 2024** (TUIK, via the provincial directorate). Cereal share is not targeted; it follows from the rotations. The achieved shares and RMSE are in the report.
5. **Per-cell engine run.** The full field pipeline runs on each cell: climate profile, candidate generation, simulation, Pareto picking, with the cell's POWER weather (1991 to last year, CHIRPS-corrected where available) and SoilGrids soil. Strategies are scored against the highest-weight baseline rotation of the cell.
6. **Adoption scenario.** A fraction `a` (10 %, 30 %, 50 %) of each cell's irrigated area, taken proportionally from every baseline rotation, switches to that cell's archetype strategy. A crop can lose at most its baseline area share. Change in basin irrigation demand:

```
dW(q) = sum_cells  irrigated_ha * a * ( W_strategy(q) - W_baseline_mix(q) )     [Mm3/yr], q in {p10,p50,p90}
```

   Quantiles are summed across cells (this assumes perfectly correlated weather, so the band is wide) and then ordered.
7. **Horizons.** "5 years" uses current climate; "10 years" adds a **trend continuation** (per-cell Sen slope of annual mean temperature x 1 decade, added to Tmax/Tmin/T, ET0 recomputed; rain unchanged).
8. **Production.** Per-crop yield comes from one-step monoculture runs of each (crop, irrigation) pair on the cell weather; production change = area switched x yield difference, summed per crop.
9. **GRACE trend and volume.** Monthly CSR GRACE/GRACE-FO RL06.3 mascon `lwe_thickness` is averaged over the bounding box (land mask, cos-lat weights). An OLS linear trend is fit and its 95 % CI uses an AR(1) effective sample size. Volume = trend x bounding-box area (spherical rectangle). Current report: -1.22 cm/yr, about -534 Mm3/yr.
10. **Offset %.** `offset = - groundwater_share * dW / |GRACE loss| * 100` with `groundwater_share = 1` (assume all demand change is groundwater). Reported as a band (p10-p90).
11. **Plausibility check.** The modelled baseline demand is shown next to published basin figures (about 1.9 to 3.7 bcm/yr, secondary sources). Model value is crop *net* requirement, so it is lower than real abstraction.

## 10. Konya agro-microclimate zones

Rotacast covers **Konya province only**. The field API rejects points outside the province or on a lake
(HTTP 422, `outside_konya` / `on_lake`). The province is split into **7 agro-microclimate zones**
(`data/zones/konya_zones.geojson`, built by `backend/scripts/build_konya_zones.py`, code in `backend/rotacast/zones/`).

**Why expert zones and not clustering.** Zone *boundaries* change slowly and are already described by official
climate classifications and the regional literature. Deriving them from raw multi-year satellite grids (MODIS LST,
PET) needs hours of server-side processing and adds little for a 7-class map. So the boundaries are expert-defined
and physically refined; the data is used to **profile and check** each zone. Every field is still analysed with its
own satellite data (NDVI, CHIRPS, SoilGrids, POWER, SRTM).

1. **Districts.** The 31 districts (geoBoundaries ADM2) are grouped into 7 zones (`zones/definitions.py`):
   Southern Taurus highlands; Seydişehir–Suğla humid transition basin; Beyşehir lake district; western transition
   belt (Akşehir–Ilgın–Yunak); central plain (Konya–Çumra); northern steppe and Tuz Gölü fringe; Karapınar–Ereğli
   very dry belt.
2. **Taurus rule.** On a 0.01° grid (~1 km), cells at or above **1500 m** and south of **37.75° N** in the districts
   bordering the Taurus (Seydişehir, Akören, Meram, Güneysınır, Halkapınar, Ereğli, Beyşehir) move to the Taurus
   zone. Elevation is from SRTM-derived terrain tiles (zoom 9). The mask is smoothed (~2 km closing and opening,
   patches < 25 km² dropped, holes < 25 km² filled) so the line follows mountains, not single pixels.
3. **Lake rule.** Land within **8 km** of Beyşehir Gölü joins the Beyşehir zone (applied after the Taurus rule).
4. **Lakes.** Beyşehir Gölü, Tuz Gölü and Suğla Gölü (OpenStreetMap) are cut out of all zones.
5. **Profiles.** Each zone carries the **MGM 1991–2020 climate classifications** of its stations (12 MGM stations
   in Konya: Aydeniz drought coefficient, Erinç precipitation-effectiveness index, De Martonne index, Trewartha
   winter/summer means, Thornthwaite class) and a **NASA POWER 2001–2025 climatology** at each station (frost days,
   spring/autumn frost days, warmest/coldest month mean, humidity). Zone elevation band = p10/p50/p90 of the grid.
6. **Field position.** The field report's `zone.elevation_position` compares the field elevation with the zone band:
   below the p10–p50 midpoint = `low` (valley floor / plain), above the p50–p90 midpoint = `high` (upper slopes).

**How the official data supports the zones.** Erinç index (higher = wetter): Seydişehir 42.3, Hadim 37.5,
Beyşehir 29.6, Akşehir 28.8, Yunak 25.8, Ilgın 23.8, Kulu 21.0, Konya 18.1, Cihanbeyli 17.4, Çumra 16.8,
Ereğli 15.7, Karapınar 15.4. Thornthwaite puts Konya, Çumra, Karapınar, Ereğli and Cihanbeyli in D (semi-arid),
the western and northern stations in C1, Hadim in C2 and Seydişehir in B1 (humid). NASA POWER frost days range from
about 86/yr (Cihanbeyli) to 118/yr (Hadim). This is why Yunak sits in the western transition belt and Kulu/Cihanbeyli
form their own northern zone instead of joining the central plain.

**Limitations.** Zone lines follow district borders except where the two physical rules apply; a field near a line
can share traits of both zones. NASA POWER is a ~50 km grid, so nearby stations (Seydişehir and Beyşehir; Karapınar
and Ereğli) get the same POWER values; the MGM indices separate them. Akşehir Gölü is mostly dry and not mapped.
The sub-label "irrigated plain microclimate" is not mapped; irrigation is a field input instead.

### 10.1 Zone crop whitelist (`data/zones/zone_crops.json`)

Each zone carries a list of crops **documented in that zone by an official or primary source**, manually verified
by the team on 2026-11-14. No crop is added from agronomic inference or analogy with other regions.

| Status | Rule | In the app |
|---|---|---|
| `verified` | District production record (MEVKA 2019 reports, TÜİK 2018 data), geographical indication (TÜRKPATENT) or official Konya study (İl Tarım medicinal-aromatic survey) | Listed |
| `pilot` | Official trial or support project in the zone (İl Tarım, Büyükşehir, TAGEM) | Listed with a "Pilot" tag; never a recommendation |
| excluded | No local evidence found (e.g. kiwi, blueberry, asparagus, Salicornia, caper, aloe vera, ginseng, teff, goji, quinoa) | Kept in the file for traceability, never returned by the API |

`caution: true` marks crops that are really grown in the zone but should not be expanded because of water or
environmental risk (groundwater restriction in the central plain and Karapınar–Ereğli, Beyşehir lake budget).
Zone-level notes carry these warnings with their source.

**Verified is not a recommendation.** Many comparable district records come from 2019 MEVKA reports based on 2018
TÜİK data: "verified" means the crop is documented in the area, not that 2026 area or profit is known. A crop may
enter a strategy card only after this chain: zone evidence → field climate → water budget → soil/salinity →
market/processing. Today the list is shown in the zone card only; the rotation engine does not yet filter by it.
A specialty crop may carry a `documented_yield` (`kg_da`, `year`, `basis`, `source`, bilingual `note`): an official
province mean (today only cumin 50 and anise 72 kg/da, TÜİK 2024 via the İl Tarım "2026 Konya Tarımı" book, Table 6).
It is shown as documentation only: it is not a forecast for the user's field and no income is computed from it
because there is no verified farm-gate price. Sorghum pilots carry no `engine` mapping: the official project is on
silage sorghum while the engine's `sorghum` is grain sorghum, so the trial row is "not modelled" and shows no numbers.
Each crop's `engine` field maps it to the engine crop ids where one exists (e.g. wheat → `wheat_winter`).

## 11. Limitations

Please read these before quoting any number.

- **Single-season simulator.** Each rotation step is one season of one crop. Perennials (alfalfa, sainfoin) need multi-year stands and are **excluded from generated candidates** (they can still appear in a farmer's own rotation).
- **The basin figure is an order-of-magnitude scenario**, not a forecast or a water budget. It scales with the stated assumptions (irrigated share, baseline mix, adoption, groundwater share). Offsets at 30-50 % adoption can exceed 100 % and should not be read literally; **lead with the 10 % adoption case**.
- **Market plausibility.** Potato is **excluded from basin strategies** (so it can stay in the baseline but is never recommended at scale), and any crop whose basin production would **expand by more than 25 % of its baseline production** is **flagged as market-implausible**. There is no price feedback: prices are fixed 2024-25 farm-gate levels, so a strategy that adds a lot of one crop would in reality depress its price. Flags are reported per scenario as `market_flags` / `market_plausible` (`BasinParams.exclude_crops`, `BasinParams.max_production_increase`); the numbers themselves are not altered. The report's `headline` block quotes only the 10 % adoption scenario; 30 % and 50 % are sensitivity runs.
- **Trend continuation only.** The 10-year horizon adds the observed temperature trend; no rain change, no CO2 effect, no adaptation, no climate-model projection.
- **No economic feedback.** Fixed prices, fixed costs, no subsidies, no quota rules, no labour or machinery limits, instant adoption (steady-state rates, no ramp).
- **Coarse weather.** One POWER cell (about 50 x 60 km) and one soil profile per basin cell; rain is rescaled to satellite monthly totals (5-10 km pixels), so single storms and sub-cell variability are not captured. Rain correction is only as good as CHIRPS in that area.
- **Simplified crop model.** Single Kc, no capillary rise, 100 % irrigation efficiency unless an irrigation method is given (section 11), no explicit evaporation layers, no nutrient, pest, disease or variety effects, a heuristic heat/frost yield penalty, and `Ky` values partly approximate. Yields are potential-based and not calibrated to TUIK/FAOSTAT.
- **Per-crop basin yields** ignore rotation effects on soil water (monoculture runs).
- **Irrigation demand is net crop requirement**, not abstraction: efficiency losses, return flows, surface-water use and orchards are not modelled.
- **GRACE** is total water storage (groundwater, soil moisture, surface water, snow) at a ~300 km footprint, not groundwater alone and not field-resolved. The bounding box is not the hydrological basin boundary.
- **Baseline mix** covers only four rotations and is calibrated to province-wide statistics, not to the box; real farms differ.
- **Field Memory** is from 250 m pixels: a pixel can mix crops, small or fragmented fields are noisy, and the bare-soil threshold is inferred, not measured.
- **Uncertainty bands** reflect weather variability across start years only.
- **Not agronomic advice.** Outputs are decision support. The report lists what to check with an agronomist, extension service or market before changing a rotation.

## 11. Optional field inputs (API v1.2; `docs/CONTRACTS.md` section 6)

All inputs are optional; a request without them gives exactly the v1.1 report (checked by `tests/test_field_details.py`
against `tests/fixtures/konya_default_strategies.json`). Every value the user typed becomes a fact with `source_id: "user"`.

- **Field polygon** (`geometry.py`): ring closed/opened, self-intersection checked on non-adjacent edges, area by the spherical
  (Chamberlain-Duquette / `@turf/area`) formula with R = 6 378 137 m, allowed 0.01-10 000 ha; lat/lon become the planar
  centroid (rounded to 6 decimals). The polygon is recorded only: MODIS (250 m) and POWER (0.5 deg) are still sampled at the centroid, which each
  strategy states in `evidence.gaps` (planned: 30 m HLS).
- **Soil override**: given clay / sand / SOC / pH replace the SoilGrids values; silt = 100 - clay - sand; fc, wp and TAW are recomputed with Saxton & Rawls (2006)
  (`saxton_rawls_2006`) and the same profile drives the simulation. If only a USDA texture class is given, the representative clay/sand
  of that class are used. These are the area centroids of each class in the clay-sand plane of the USDA texture triangle (class
  boundaries as in `usda_texture_class`, USDA-NRCS soil texture triangle, Soil Survey Manual 2017): clay 63/20, clay loam 33/33,
  silty clay loam 33/10, silty clay 47/7, loam 18/42, silt loam 13/22, sandy loam 10/65, sandy clay loam 27/61, sandy clay 41/52,
  loamy sand 6/82, sand 3/92, silt 5/8 (clay %/sand %). If only one of clay/sand is given, the other comes from the class (if given) or SoilGrids and is capped so that clay + sand <= 100.
- **Excluded crops** go to `constraints.exclude_crops` of candidate generation. The user's own current rotation is never changed.
- **Irrigation method**: gross water = net crop irrigation / field application efficiency. Typical efficiencies: flood 0.55, furrow 0.65, sprinkler 0.75, drip 0.90 (FAO training-manual typical values are surface ~0.60, sprinkler ~0.75, drip ~0.90; the flood/furrow split of surface irrigation is our assumption)
  (`IRRIGATION_EFFICIENCY` in `engine/rotations.py`; source id `irrigation_efficiency`, FAO Irrigation Water Management Training Manual No. 5, *Irrigation Methods*, Brouwer et al. 1989).
  These are rounded typical values, not field measurements. `water_m3_ha_yr` and the water cost inside income are gross; `irrigation_mm_yr` stays net crop irrigation.
- **Water quota**: per-ha quota = quota / polygon area (or the number itself without a polygon). Candidates are generated with `water_access` "full" (quota 0: "none"), those with p50 gross
  `water_m3_ha_yr` above the quota are dropped before picking; if fewer than 3 feasible candidates remain they stay eligible and are flagged `exceeds_quota`. `quota.relaxed` tells which case happened.
- **Declared yields**: factor = declared / regional reference (irrigated tier if the crop is irrigated in the current rotation, rainfed otherwise; a crop not in the rotation uses
  irrigated if its `irrigation_typical` is "required"). Both yield tiers of that crop are scaled in a per-request copy of the knowledge base.
- **History** is compared with the NDVI pattern of each year (winter crop = `winter_crop`, spring/summer crop = `summer_crop`, a satellite `double_crop` agrees with either); the model is not changed.
- **Applied irrigation** is compared with the modelled gross irrigation per season of that crop in the current rotation; the model is not changed.

