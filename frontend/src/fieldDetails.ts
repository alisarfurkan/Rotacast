import type { ExclusionReason, FieldDetails, IrrigationMethod, Lang, RotationStep } from './types'
import type { Key } from './i18n'

// Form state for the optional "know your field better" panel (Advanced mode). All values are strings so an
// empty input means "not given" and is omitted from the request.
export interface DetailsForm {
  texture: string
  clay: string
  sand: string
  soc: string
  ph: string
  excluded: { crop_id: string; reason: ExclusionReason }[]
  method: '' | IrrigationMethod
  quota: string
  yields: Record<string, string> // crop_id -> t/ha
  history: { year: string; crop_id: string }[]
  irrApplied: Record<string, string> // crop_id -> m3/ha
}

export const EMPTY_DETAILS: DetailsForm = {
  texture: '', clay: '', sand: '', soc: '', ph: '', excluded: [], method: '', quota: '', yields: {}, history: [], irrApplied: {},
}

// 12 USDA texture classes (as SoilProfile.texture_class). TR names mirror backend report.py::_climate_facts.
export const TEXTURES: { id: string; en: string; tr: string }[] = [
  { id: 'clay', en: 'Clay', tr: 'killi' },
  { id: 'clay loam', en: 'Clay loam', tr: 'killi tın' },
  { id: 'silty clay loam', en: 'Silty clay loam', tr: 'siltli killi tın' },
  { id: 'silty clay', en: 'Silty clay', tr: 'siltli kil' },
  { id: 'loam', en: 'Loam', tr: 'tın' },
  { id: 'silt loam', en: 'Silt loam', tr: 'siltli tın' },
  { id: 'sandy loam', en: 'Sandy loam', tr: 'kumlu tın' },
  { id: 'sandy clay loam', en: 'Sandy clay loam', tr: 'kumlu killi tın' },
  { id: 'sandy clay', en: 'Sandy clay', tr: 'kumlu kil' },
  { id: 'loamy sand', en: 'Loamy sand', tr: 'tınlı kum' },
  { id: 'sand', en: 'Sand', tr: 'kumlu' },
  { id: 'silt', en: 'Silt', tr: 'silt' },
]

export const METHODS: { id: IrrigationMethod; key: Key }[] = [
  { id: 'flood', key: 'detMFlood' }, { id: 'furrow', key: 'detMFurrow' },
  { id: 'sprinkler', key: 'detMSprinkler' }, { id: 'drip', key: 'detMDrip' },
]
export const REASONS: { id: ExclusionReason; key: Key }[] = [
  { id: 'no_equipment', key: 'detRNoEquip' }, { id: 'no_buyer', key: 'detRNoBuyer' }, { id: 'not_wanted', key: 'detRNotWanted' },
]

export const textureLabel = (id: string, lang: Lang) => TEXTURES.find((x) => x.id === id)?.[lang] ?? id

const num = (s: string): number | null => {
  const v = s.trim().replace(',', '.')
  if (v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : NaN
}

export const rotationCrops = (rot: RotationStep[]) => Array.from(new Set(rot.map((r) => r.crop_id)))

/** Request body part; undefined when nothing is filled. Values that fail to parse are dropped (validation flags them). */
export function buildDetails(f: DetailsForm, rotation: RotationStep[]): FieldDetails | undefined {
  const d: FieldDetails = {}
  const soil: NonNullable<FieldDetails['soil']> = {}
  if (f.texture) soil.texture_class = f.texture
  for (const [k, v] of [['clay_pct', f.clay], ['sand_pct', f.sand], ['soc_gkg', f.soc], ['ph', f.ph]] as const) {
    const n = num(v)
    if (n !== null && !Number.isNaN(n)) soil[k] = n
  }
  if (Object.keys(soil).length) d.soil = soil
  if (f.excluded.length) d.excluded_crops = f.excluded.map((e) => ({ crop_id: e.crop_id, reason: e.reason }))
  if (f.method) d.irrigation_method = f.method
  const q = num(f.quota)
  if (q !== null && !Number.isNaN(q)) d.water_quota_m3_yr = q
  const y: Record<string, number> = {}
  const ia: Record<string, number> = {}
  for (const c of rotationCrops(rotation)) {
    const a = num(f.yields[c] ?? ''), b = num(f.irrApplied[c] ?? '')
    if (a !== null && !Number.isNaN(a)) y[c] = a
    if (b !== null && !Number.isNaN(b)) ia[c] = b
  }
  if (Object.keys(y).length) d.yields_t_ha = y
  const hist = f.history
    .map((h) => ({ year: num(h.year), crop_id: h.crop_id }))
    .filter((h): h is { year: number; crop_id: string } => h.year !== null && !Number.isNaN(h.year))
  if (hist.length) d.history = hist
  if (Object.keys(ia).length) d.irrigation_applied_m3_ha = ia
  return Object.keys(d).length ? d : undefined
}

type T = (key: Key, vars?: Record<string, string | number>) => string

/**
 * Client-side checks matching docs/CONTRACTS.md section 6.1. Keys are dotted paths below `field_details`
 * (same shape as the server's 422 `loc`), e.g. `soil.clay_pct`, `yields_t_ha.wheat_winter`, `history`.
 */
export function validateDetails(f: DetailsForm, rotation: RotationStep[], t: T): Record<string, string> {
  const e: Record<string, string> = {}
  const range = (key: string, raw: string, min: number, max: number, exclusiveMin = false) => {
    const n = num(raw)
    if (n === null) return null
    if (Number.isNaN(n)) { e[key] = t('vNum'); return null }
    if (n < min || n > max || (exclusiveMin && n === min)) {
      e[key] = t(exclusiveMin ? 'vRangeGt' : 'vRange', { min, max })
      return null
    }
    return n
  }
  const clay = range('soil.clay_pct', f.clay, 0, 100)
  const sand = range('soil.sand_pct', f.sand, 0, 100)
  range('soil.soc_gkg', f.soc, 0, 200)
  range('soil.ph', f.ph, 3, 10)
  if (clay !== null && sand !== null && clay + sand > 100) e['soil.sand_pct'] = t('vSum')
  const q = num(f.quota)
  if (q !== null && (Number.isNaN(q) || q < 0)) e['water_quota_m3_yr'] = Number.isNaN(q) ? t('vNum') : t('vNonNeg')
  for (const c of rotationCrops(rotation)) {
    range('yields_t_ha.' + c, f.yields[c] ?? '', 0, 200, true)
    range('irrigation_applied_m3_ha.' + c, f.irrApplied[c] ?? '', 0, 30000)
  }
  const last = new Date().getFullYear() - 1
  const seen = new Set<number>()
  for (const h of f.history) {
    const n = num(h.year)
    if (n === null) continue
    if (Number.isNaN(n) || !Number.isInteger(n) || n < 2000 || n > last) { e['history'] = t('vYear', { min: 2000, max: last }); break }
    if (seen.has(n)) { e['history'] = t('vDupYear'); break }
    seen.add(n)
  }
  return e
}

const SECTIONS = ['soil', 'excluded_crops', 'irrigation_method', 'water_quota_m3_yr', 'yields_t_ha', 'history', 'irrigation_applied_m3_ha']

/** Map a FastAPI 422 `detail[].loc` to a dotted `field_details` path, or null when it is not a details field. */
export function locToPath(loc: (string | number)[]): string | null {
  const i = loc.indexOf('field_details')
  if (i < 0) return null
  const rest = loc.slice(i + 1).map(String)
  return rest.length && SECTIONS.includes(rest[0]) ? rest.join('.') : null
}

/** First error message at `prefix` or below it (`soil` matches `soil.clay_pct`). */
export function errFor(errors: Record<string, string>, prefix: string): string | undefined {
  if (errors[prefix]) return errors[prefix]
  const k = Object.keys(errors).find((x) => x.startsWith(prefix + '.'))
  return k ? errors[k] : undefined
}
