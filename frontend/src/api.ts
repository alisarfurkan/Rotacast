import type { BasinReport, FieldReport, FieldRequest } from './types'
import { areaHa } from './geometry'
import mockBasin from './mock/basinReport.konya.json'
import mockReport from './mock/fieldReport.konya.json'

/** HTTP 422 from the API: the request was understood but a value is invalid. Never falls back to the mock. */
export interface ValidationIssue { loc: (string | number)[]; msg: string }
export class ValidationError extends Error {
  issues: ValidationIssue[]
  constructor(issues: ValidationIssue[]) { super('HTTP 422'); this.issues = issues }
}

export interface AnalyzeResult { report: FieldReport; source: 'live' | 'mock-forced' | 'mock-fallback' }

const isMockForced = () => new URLSearchParams(window.location.search).get('mock') === '1'

/** Re-score the bundled demo data so priority/scenario sliders feel alive without a backend. */
function scoreMock(req: FieldRequest): FieldReport {
  const rep = structuredClone(mockReport) as unknown as FieldReport
  const w = req.priorities
  const sum = w.water + w.soil + w.income + w.erosion + w.risk || 1
  const dT = req.scenario.delta_t_c
  const dry = Math.max(0, -req.scenario.precip_change_pct)
  const stressFactor = dT * 1.8 + dry * 0.22
  for (const s of rep.strategies) {
    const b = s.score_breakdown
    const thirst = Math.min(1, s.indicators.water_m3_ha_yr.p50 / 5500)
    const waterAdj = Math.max(0, b.water - stressFactor * (0.3 + 0.9 * thirst) * 1.5)
    const riskAdj = Math.max(0, b.risk - stressFactor * 0.7)
    s.score_breakdown = { ...b, water: waterAdj, risk: riskAdj }
    s.score = Math.round(
      (w.water * waterAdj + w.soil * b.soil + w.income * b.income + w.erosion * b.erosion + w.risk * riskAdj) / sum,
    )
    const k = (1 + 0.04 * dT) * (1 + 0.004 * dry)
    const bd = s.indicators.water_m3_ha_yr
    s.indicators.water_m3_ha_yr = { p10: bd.p10 * k, p50: bd.p50 * k, p90: bd.p90 * k }
    s.indicators.heat_risk = Math.min(1, s.indicators.heat_risk * (1 + 0.12 * dT))
  }
  rep.location = { ...rep.location, lat: req.lat, lon: req.lon }
  if (req.field_polygon) {
    // The bundled demo has no v1.2 keys; only expose the boundary and its area so the UI can be exercised offline.
    const ring = req.field_polygon.coordinates[0].slice(0, -1).map(([lon, lat]) => ({ lat, lon }))
    rep.location = { ...rep.location, area_ha: +areaHa(ring).toFixed(2), polygon: req.field_polygon }
  }
  return rep
}

export async function analyzeField(req: FieldRequest): Promise<AnalyzeResult> {
  if (isMockForced()) {
    await new Promise((r) => setTimeout(r, 2600))
    return { report: scoreMock(req), source: 'mock-forced' }
  }
  try {
    const res = await fetch('/api/field/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })
    if (res.status === 422) {
      let issues: ValidationIssue[] = []
      try {
        const body = await res.json()
        if (Array.isArray(body?.detail)) issues = body.detail.map((d: { loc?: (string | number)[]; msg?: string }) => ({ loc: d.loc ?? [], msg: String(d.msg ?? '') }))
        else if (typeof body?.detail === 'string') issues = [{ loc: [], msg: body.detail }]
      } catch { /* body is not JSON */ }
      throw new ValidationError(issues)
    }
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const report = (await res.json()) as FieldReport
    if (!report || !Array.isArray(report.strategies)) throw new Error('bad payload')
    return { report, source: 'live' }
  } catch (err) {
    if (err instanceof ValidationError) throw err
    await new Promise((r) => setTimeout(r, 2600))
    return { report: scoreMock(req), source: 'mock-fallback' }
  }
}

export async function getBasin(): Promise<{ report: BasinReport; mock: boolean }> {
  if (!isMockForced()) {
    try {
      const res = await fetch('/api/basin/konya')
      if (!res.ok) throw new Error('HTTP ' + res.status)
      const report = (await res.json()) as BasinReport
      if (!report || !report.scenarios) throw new Error('bad payload')
      return { report, mock: false }
    } catch { /* fall through to mock */ }
  }
  return { report: mockBasin as unknown as BasinReport, mock: true }
}
