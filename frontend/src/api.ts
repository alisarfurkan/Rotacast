import type { FieldReport, FieldRequest } from './types'
import mockReport from './mock/fieldReport.konya.json'

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
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const report = (await res.json()) as FieldReport
    if (!report || !Array.isArray(report.strategies)) throw new Error('bad payload')
    return { report, source: 'live' }
  } catch {
    await new Promise((r) => setTimeout(r, 2600))
    return { report: scoreMock(req), source: 'mock-fallback' }
  }
}
