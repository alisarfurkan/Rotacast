import type { Fact, Indicators, Lang, Strategy } from './types'
import { pick } from './util'

/** Relative change below this share is shown as "similar" (=) in Beginner mode. The only place this number lives. */
export const SIMILAR_THRESHOLD = 0.05

/** Port of backend/rotacast/engine/scoring.py::soil_composite (0-1): 40 % N balance, 30 % residue, 30 % cover. */
export function soilComposite(ind: Pick<Indicators, 'n_balance_kg_ha_yr' | 'residue_index' | 'soil_cover_days_yr'>): number {
  const clip = (v: number) => Math.min(1, Math.max(0, v))
  const nTerm = clip((ind.n_balance_kg_ha_yr + 10) / 40)
  const res = clip(ind.residue_index)
  const cover = clip(ind.soil_cover_days_yr / 365)
  return 0.4 * nTerm + 0.3 * res + 0.3 * cover
}

export type Trend = 'up' | 'down' | 'same'

/** Direction of `value` relative to `base`; within SIMILAR_THRESHOLD (relative to |base|) counts as same. */
export function trend(value: number, base: number): Trend {
  const diff = value - base
  if (diff === 0) return 'same'
  if (base === 0) return diff > 0 ? 'up' : 'down'
  if (Math.abs(diff) / Math.abs(base) < SIMILAR_THRESHOLD) return 'same'
  return diff > 0 ? 'up' : 'down'
}

export interface SimpleDeltas { water: Trend; income: Trend; soil: Trend }
export function simpleDeltas(s: Strategy, base: Strategy): SimpleDeltas {
  return {
    water: trend(s.indicators.water_m3_ha_yr.p50, base.indicators.water_m3_ha_yr.p50),
    income: trend(s.indicators.income_usd_ha_yr.p50, base.indicators.income_usd_ha_yr.p50),
    soil: trend(soilComposite(s.indicators), soilComposite(base.indicators)),
  }
}

/** Main crops in cycle order, e.g. "Mercimek → Ayçiçeği → Nohut → Mısır". */
export function cropChain(s: Strategy, lang: Lang): string {
  return s.calendar
    .filter((e) => e.kind !== 'cover')
    .sort((a, b) => a.year - b.year)
    .map((e) => pick(e.crop_name, lang))
    .join(' → ')
}

/**
 * Pick the three "about your field" sentences from report.facts. Facts have no key field, so they are
 * identified by (unit, source_id), which the backend's report.py::_climate_facts fixes:
 *  - bare:    unit "days"    + source "modis_mod13q1"  (the only fact with that pair; frost-free days is nasa_power)
 *  - heat:    unit "days/yr" + source "nasa_power"     (days above 35 °C, early vs late period)
 *  - deficit: FIRST fact with unit "mm" + source "nasa_power". The ET0-trend fact has the same unit/source but
 *             _climate_facts adds the deficit fact first (the mock report has the same order: f1 deficit, f3 ET0 trend).
 * A sentence whose fact is missing is skipped. Order shown: bare, heat, deficit.
 */
export function aboutFacts(facts: Fact[], lang: Lang): string[] {
  const bare = facts.find((f) => f.unit === 'days' && f.source_id === 'modis_mod13q1')
  const heat = facts.find((f) => f.unit === 'days/yr' && f.source_id === 'nasa_power')
  const deficit = facts.find((f) => f.unit === 'mm' && f.source_id === 'nasa_power')
  return [bare, heat, deficit].filter((f): f is Fact => !!f).map((f) => pick(f.text, lang))
}
