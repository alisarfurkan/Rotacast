// FieldReport request/response types - mirrors docs/CONTRACTS.md section 4.

export type Lang = 'en' | 'tr'
export interface I18nText { en: string; tr: string }
export interface Band { p10: number; p50: number; p90: number }

export type Irrigation = 'none' | 'deficit' | 'full'
export type WaterAccess = 'none' | 'limited' | 'full'

export interface RotationStep { crop_id: string; irrigation: Irrigation }

export interface Priorities { water: number; soil: number; income: number; erosion: number; risk: number }

export type Mode = 'beginner' | 'advanced'

// --- v1.2 request additions (docs/CONTRACTS.md section 6.1); all optional ---
export interface FieldPolygon { type: 'Polygon'; coordinates: number[][][] } // [lon, lat], closed outer ring
export type ExclusionReason = 'no_equipment' | 'no_buyer' | 'not_wanted'
export type IrrigationMethod = 'flood' | 'furrow' | 'sprinkler' | 'drip'
export interface FieldDetails {
  soil?: { texture_class?: string; clay_pct?: number; sand_pct?: number; soc_gkg?: number; ph?: number }
  excluded_crops?: { crop_id: string; reason: ExclusionReason }[]
  irrigation_method?: IrrigationMethod
  water_quota_m3_yr?: number
  yields_t_ha?: Record<string, number>
  history?: { year: number; crop_id: string }[]
  irrigation_applied_m3_ha?: Record<string, number>
}

export interface FieldRequest {
  lat: number
  lon: number
  field_polygon?: FieldPolygon
  field_details?: FieldDetails
  current_rotation: RotationStep[]
  constraints: { water_access: WaterAccess; max_irrigated_share: number }
  priorities: Priorities
  scenario: { delta_t_c: number; precip_change_pct: number }
  lang: Lang
}

export interface SourceInfo { id: string; name: string; detail: string; url: string }

export interface ClimateAnnual {
  year: number; precip_mm: number; et0_mm: number; tmean_c: number
  gdd0: number; heat_days_35: number; frost_days: number
}
export interface MonthlyNormal {
  month: number; precip_mm: number; et0_mm: number; tmean_c: number; tmin_c: number; tmax_c: number
}
export interface ShiftMetric {
  id: string; label: I18nText; unit: string
  early: number; late: number; delta: number; trend_per_decade: number; p_value: number
}
export interface Climate {
  period: [number, number]
  annual: ClimateAnnual[]
  monthly_normals: MonthlyNormal[]
  frost: { last_spring_doy: Band; first_fall_doy: Band; frost_free_days: Band }
  water_balance: { aridity_index: number; annual_deficit_mm: number }
  shift: { early: [number, number]; late: [number, number]; metrics: ShiftMetric[] }
}

export interface NdviPoint { date: string; ndvi: number; ndvi_smooth: number }
export interface YearPattern {
  year: number; greenup_doy: number; peak_doy: number; peak_ndvi: number
  senescence_doy: number; season_integral: number; anomaly_z: number
  stress: boolean; pattern: string
}
export interface FieldMemory {
  ndvi: NdviPoint[]
  years: YearPattern[]
  bare_probability: { doy: number; p_bare: number }[]
  bare_windows: { start_doy: number; end_doy: number; probability: number }[]
  stress_years: number[]
}

export interface Soil {
  clay_pct: number; sand_pct: number; silt_pct: number; soc_gkg: number; ph: number
  texture_class: string; taw_mm_per_m: number; source_id: string
}
export interface Terrain { elevation_m: number; slope_pct: number }

export interface CalendarEntry {
  year: number; crop_id: string; crop_name: I18nText; irrigation: Irrigation
  sow: string; harvest: string; kind: 'main' | 'cover'
}
export interface Indicators {
  irrigation_mm_yr: Band
  water_m3_ha_yr: Band
  yield_ratio: Band
  stress_days_yr: Band
  frost_risk: number
  heat_risk: number
  n_balance_kg_ha_yr: number
  residue_index: number
  soil_cover_days_yr: number
  erosion_rel: number
  pest_break: number
  income_usd_ha_yr: Band
}
export interface ScoreBreakdown { water: number; soil: number; income: number; erosion: number; risk: number }
export interface EvidenceItem { text: I18nText; facts?: string[] }
export interface Evidence {
  why: EvidenceItem[]
  benefits: EvidenceItem[]
  gaps: { text: I18nText }[]
  risks: { text: I18nText; check_with?: string }[]
}
export interface Strategy {
  id: string
  archetype: 'baseline' | 'water_saver' | 'soil_builder' | 'balanced_income' | string
  name: I18nText
  cycle_years: number
  calendar: CalendarEntry[]
  indicators: Indicators
  score: number
  score_breakdown: ScoreBreakdown
  evidence: Evidence
  exceeds_quota?: boolean // v1.2: only with water_quota_m3_yr
}
export interface Fact { id: string; text: I18nText; value: number; unit: string; source_id: string }

// --- v1.2 response additions (docs/CONTRACTS.md section 6.3); all optional ---
export interface UserInput {
  id: string // polygon | soil | excluded_crops | irrigation_method | water_quota | yields | history | irrigation_applied
  label: I18nText
  value: I18nText
  model?: I18nText | null
  fact?: string
}
export interface YieldCheck { crop_id: string; declared_t_ha: number; regional_t_ha: number; factor: number }
export interface HistoryCheck {
  n_years: number; n_agree: number; agreement: number | null // null when no declared year has satellite data
  years: { year: number; crop_id: string; declared_pattern: string; satellite_pattern: string | null; agree: boolean | null }[]
}
export interface IrrigationCheck { crop_id: string; declared_m3_ha: number; modelled_m3_ha: number | null; diff_pct: number | null }

export interface FieldReport {
  location: { lat: number; lon: number; elevation_m: number; label: string; area_ha?: number; polygon?: FieldPolygon }
  user_inputs?: UserInput[]
  irrigation?: { method: string; efficiency: number; source_id: string }
  quota?: { quota_m3_yr: number; quota_m3_ha_yr: number; basis: 'field_total' | 'per_ha'; baseline_exceeds: boolean; n_candidates_excluded: number; relaxed?: boolean }
  yield_check?: YieldCheck[]
  history_check?: HistoryCheck
  irrigation_check?: IrrigationCheck[]
  sources: SourceInfo[]
  climate: Climate
  field_memory: FieldMemory
  soil: Soil
  terrain: Terrain
  strategies: Strategy[]
  facts: Fact[]
  disclaimer: I18nText
}

// BasinReport (docs/CONTRACTS.md section 5)
export interface BasinCellStrategy {
  score: number; rotation_name: I18nText; water_m3_ha: Band; water_change_m3_ha_p50: number
}
export interface BasinCell {
  id: string; lat: number; lon: number; bounds: number[]; clip: number[]; area_km2: number
  cropland_ha: number; irrigated_ha: number; baseline_water_m3_ha: number
  best_strategy: { archetype: string; name: I18nText; score: number }
  strategies: Record<string, BasinCellStrategy>
}
export interface BasinScenario {
  climate: string
  irrigation_change_mm3_yr: Band
  grace_offset_pct: Band | null
  production_change_t_yr: { crop_id: string; name: I18nText; change_t_yr: number }[]
  market_flags?: { crop_id: string; increase_pct: number | null }[]
  market_plausible?: boolean
}
export interface BasinHeadline {
  adoption: number; horizon: number; note: I18nText
  scenarios: { archetype: string; name: I18nText; water_change_mm3_yr: Band; grace_offset_pct: Band | null
    market_plausible: boolean; market_flags: { crop_id: string; increase_pct: number | null }[] }[]
}
export interface BasinReport {
  scenario_notice: I18nText
  region: { id: string; name: I18nText; bbox: number[]; bbox_area_km2: number }
  totals: { n_cells: number; cropland_ha: number; irrigated_ha: number }
  strategies: { id: string; name: I18nText }[]
  adoption_rates: number[]
  horizons: number[]
  headline?: BasinHeadline
  cells: BasinCell[]
  scenarios: Record<string, Record<string, Record<string, BasinScenario>>>
  grace: {
    available: boolean; trend_cm_yr: number | null; trend_ci95_cm_yr: number[] | null
    volume_change_mm3_yr: number | null; volume_change_ci95_mm3_yr: number[] | null
    loss_mm3_yr: number | null; series: { date: string; tws_cm: number }[]; note: I18nText
  }
  assumptions: { id: string; label: I18nText; value: unknown; source: string }[]
  limitations: I18nText[]
  sources: { id: string; name: string; url: string }[]
}
