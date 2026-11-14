import { useCallback, useEffect, useRef, useState } from 'react'
import { LangContext, useT } from './ctx'
import { analyzeField, type AnalyzeResult } from './api'
import type { FieldReport, Lang, Priorities, RotationStep, WaterAccess } from './types'
import { Header, type Tab } from './components/Header'
import { InputPanel, type Scenario } from './components/InputPanel'
import { KONYA, type Point } from './components/FieldPicker'
import { Loading } from './components/Loading'
import { FieldMemory } from './components/FieldMemory'
import { ClimateShift } from './components/ClimateShift'
import { Strategies } from './components/Strategies'
import { EvidenceDrawer } from './components/EvidenceDrawer'
import { BasinView } from './components/BasinView'
import { Footer } from './components/Footer'

const initialLang = (): Lang => {
  try {
    const s = localStorage.getItem('rotacast.lang')
    if (s === 'en' || s === 'tr') return s
  } catch { /* ignore */ }
  return 'tr'
}

const DEFAULT_ROTATION: RotationStep[] = [
  { crop_id: 'wheat_winter', irrigation: 'none' },
  { crop_id: 'sugar_beet', irrigation: 'full' },
  { crop_id: 'maize_grain', irrigation: 'full' },
]
const ACCESS_SHARE: Record<WaterAccess, number> = { none: 0, limited: 0.5, full: 1 }

export default function App() {
  const [lang, setLangState] = useState<Lang>(initialLang)
  const setLang = (l: Lang) => {
    setLangState(l)
    try { localStorage.setItem('rotacast.lang', l) } catch { /* ignore */ }
  }
  useEffect(() => { document.documentElement.lang = lang }, [lang])
  return (
    <LangContext.Provider value={lang}>
      <Shell lang={lang} setLang={setLang} />
    </LangContext.Provider>
  )
}

function Shell({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  const t = useT()
  const [tab, setTab] = useState<Tab>('field')
  const [point, setPoint] = useState<Point | null>(null)
  const [rotation, setRotation] = useState<RotationStep[]>(DEFAULT_ROTATION)
  const [waterAccess, setWaterAccess] = useState<WaterAccess>('limited')
  const [priorities, setPriorities] = useState<Priorities>({ water: 0.3, soil: 0.25, income: 0.25, erosion: 0.1, risk: 0.1 })
  const [scenario, setScenario] = useState<Scenario>({ delta_t_c: 0, precip_change_pct: 0 })
  const [report, setReport] = useState<FieldReport | null>(null)
  const [source, setSource] = useState<AnalyzeResult['source'] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const seq = useRef(0)

  const run = useCallback(async (p: Point, quiet: boolean) => {
    const my = ++seq.current
    if (!quiet) {
      setLoading(true)
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }
    setError(null)
    try {
      const res = await analyzeField({
        lat: p.lat, lon: p.lon, current_rotation: rotation,
        constraints: { water_access: waterAccess, max_irrigated_share: ACCESS_SHARE[waterAccess] },
        priorities, scenario, lang,
      })
      if (my !== seq.current) return
      setReport(res.report)
      setSource(res.source)
      if (!quiet) setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch {
      if (my === seq.current) setError(t('error'))
    } finally {
      if (my === seq.current) setLoading(false)
    }
  }, [rotation, waterAccess, priorities, scenario, lang, t])

  // Live re-scoring when sliders move after a first analysis (debounced).
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    if (!report || !point || loading) return
    const id = setTimeout(() => run(point, true), 500)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priorities, scenario])

  const openStrategy = report?.strategies.find((s) => s.id === openId) ?? null

  return (
    <div className="min-h-screen">
      <Header lang={lang} setLang={setLang} tab={tab} setTab={setTab} />
      <div className="bg-sunsoft text-ink text-xs md:text-[13px] text-center px-4 py-1.5 border-b border-line">{t('supportNote')}</div>
      <main className="mx-auto max-w-[1500px] px-4 md:px-8 py-5">
        {tab === 'basin' ? <BasinView /> : (
          <div className="flex flex-col gap-8">
            <div className="mx-auto w-full max-w-[1180px]">
              {!report && !loading && (
                <section className="text-center mb-6 rise">
                  <svg viewBox="0 0 320 50" className="mx-auto w-full max-w-xs mb-3" aria-hidden>
                    {Array.from({ length: 16 }, (_, i) => (
                      <rect key={i} x={i * 20} y={5} width="18" height="40" rx="3"
                        fill={['#6b4a2b', '#a98457', '#d9c78a', '#9fc66b', '#3f8a32', '#3f8a32', '#9fc66b', '#d9c78a', '#a98457', '#6b4a2b', '#6b4a2b', '#6b4a2b', '#a98457', '#d9c78a', '#9fc66b', '#6b4a2b'][i]} opacity={0.9} />
                    ))}
                  </svg>
                  <h2 className="font-display text-2xl md:text-3xl font-extrabold mb-2">{t('emptyTitle')}</h2>
                  <p className="text-muted max-w-2xl mx-auto">{t('emptyText')}</p>
                </section>
              )}
              <InputPanel point={point} onPick={setPoint} rotation={rotation} setRotation={setRotation}
                waterAccess={waterAccess} setWaterAccess={setWaterAccess} priorities={priorities} setPriorities={setPriorities}
                scenario={scenario} setScenario={setScenario} loading={loading} error={error}
                onAnalyze={() => point && run(point, false)}
                onDemo={() => { setPoint(KONYA); run(KONYA, false) }} />
            </div>
            <div ref={resultsRef} className="flex flex-col gap-6 min-w-0 scroll-mt-4">
              {loading ? <div className="mx-auto w-full max-w-2xl"><Loading /></div> : !report ? null : (
                <>
                  {source && source !== 'live' && (
                    <div role="status" className="rounded-xl bg-sunsoft border border-sun px-4 py-2 text-sm">
                      {t(source === 'mock-forced' ? 'mockForced' : 'mockBanner')} {t('scenarioMock')}
                    </div>
                  )}
                  <div className="text-xs text-muted">📍 {report.location.label} · {Math.round(report.location.elevation_m)} m</div>
                  <Strategies strategies={report.strategies} onOpen={setOpenId} />
                  <FieldMemory fm={report.field_memory} />
                  <ClimateShift climate={report.climate} />
                </>
              )}
            </div>
          </div>
        )}
      </main>
      <Footer report={report} />
      <EvidenceDrawer s={openStrategy} facts={report?.facts ?? []} sources={report?.sources ?? []} onClose={() => setOpenId(null)} />
    </div>
  )
}
