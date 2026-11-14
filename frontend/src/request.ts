import type { FieldRequest, Lang, Mode, Priorities, RotationStep, WaterAccess } from './types'
import type { Point } from './components/FieldPicker'
import type { Scenario } from './components/InputPanel'
import { buildDetails, type DetailsForm } from './fieldDetails'
import { MAX_HA, MIN_HA, areaHa, centroid, selfIntersects, toGeoJSON } from './geometry'

export const ACCESS_SHARE: Record<WaterAccess, number> = { none: 0, limited: 0.5, full: 1 }

export interface Inputs {
  point: Point | null
  polygon: Point[] | null // closed boundary (>= 3 vertices, first point not repeated), Advanced only
  rotation: RotationStep[]
  waterAccess: WaterAccess
  priorities: Priorities
  scenario: Scenario
  details: DetailsForm
}

export type PolygonProblem = 'selfx' | 'size' | null
export function polygonProblem(poly: Point[] | null): PolygonProblem {
  if (!poly || poly.length < 3) return null
  if (selfIntersects(poly)) return 'selfx'
  const ha = areaHa(poly)
  return ha < MIN_HA || ha > MAX_HA ? 'size' : null
}

/**
 * The ONE place the request is derived from (state, mode).
 * Beginner: scenario is always 0/0 and neither field_polygon nor field_details is sent.
 * Advanced: scenario as set; a valid polygon replaces the point (lat/lon = centroid); field_details only if filled.
 * Returns null when there is no location yet or the polygon is unusable (the UI shows why and does not send).
 */
export function buildRequest(inp: Inputs, mode: Mode, lang: Lang): FieldRequest | null {
  const advanced = mode === 'advanced'
  const poly = advanced && inp.polygon && inp.polygon.length >= 3 ? inp.polygon : null
  if (poly && polygonProblem(poly)) return null
  const loc = poly ? centroid(poly) : inp.point
  if (!loc) return null
  const req: FieldRequest = {
    lat: +loc.lat.toFixed(5), lon: +loc.lon.toFixed(5),
    current_rotation: inp.rotation,
    constraints: { water_access: inp.waterAccess, max_irrigated_share: ACCESS_SHARE[inp.waterAccess] },
    priorities: inp.priorities,
    scenario: advanced ? inp.scenario : { delta_t_c: 0, precip_change_pct: 0 },
    lang,
  }
  if (poly) req.field_polygon = toGeoJSON(poly)
  if (advanced) {
    const d = buildDetails(inp.details, inp.rotation)
    if (d) req.field_details = d
  }
  return req
}

/** Stable comparison key: language does not change the numbers (both languages are in the report). */
export const requestKey = (r: FieldRequest) => JSON.stringify({ ...r, lang: undefined })
