import type { BasinReport, FieldReport, FieldRequest, ZonesData } from './types'
import mockBasin from './mock/basinReport.konya.json'
import mockReport from './mock/fieldReport.konya.json'
import mockZones from './mock/zones.konya.json'

/** Rejection from the API that is the user's input problem (outside Konya, on a lake), not an outage. */
export class AnalyzeError extends Error {
  code: string
  constructor(code: string, message: string) { super(message); this.code = code }
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
  return rep  // location stays Çumra: the demo numbers never belong to another point
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
      const body = await res.json().catch(() => null)
      const d = body?.detail
      if (d && typeof d === 'object' && (d.code === 'outside_konya' || d.code === 'on_lake')) {
        throw new AnalyzeError(d.code, String(d.message ?? ''))
      }
    }
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const report = (await res.json()) as FieldReport
    if (!report || !Array.isArray(report.strategies)) throw new Error('bad payload')
    return { report, source: 'live' }
  } catch (e) {
    if (e instanceof AnalyzeError) throw e
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

let zonesCache: Promise<ZonesData> | null = null

/** Konya agro-microclimate zones, boundary and lakes; falls back to the bundled copy when the API is unreachable. */
export function getZones(): Promise<ZonesData> {
  if (!zonesCache) {
    zonesCache = (async () => {
      if (!isMockForced()) {
        try {
          const res = await fetch('/api/zones')
          if (!res.ok) throw new Error('HTTP ' + res.status)
          const d = (await res.json()) as ZonesData
          if (!d?.zones?.features?.length) throw new Error('bad payload')
          return d
        } catch { /* fall through to mock */ }
      }
      return mockZones as unknown as ZonesData
    })()
  }
  return zonesCache
}
