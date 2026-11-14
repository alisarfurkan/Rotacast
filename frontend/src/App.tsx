import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LangContext, useT } from './ctx'
import { analyzeField, ValidationError, type AnalyzeResult } from './api'
import type { FieldReport, Lang, Mode, Priorities, RotationStep, WaterAccess } from './types'
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
import { fmt } from './util'
import { SimpleResults, AboutField } from './components/SimpleResults'
import { UserInputs } from './components/UserInputs'
import { EMPTY_DETAILS, locToPath, validateDetails, type DetailsForm } from './fieldDetails'
import { areaHa, centroid } from './geometry'
import { buildRequest, polygonProblem, requestKey, type Inputs } from './request'

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

const initialMode = (): Mode => {
  try {
    const s = localStorage.getItem('rotacast.mode')
    if (s === 'beginner' || s === 'advanced') return s
  } catch { /* ignore */ }
  return 'beginner'
}


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
  const [mode, setModeState] = useState<Mode>(initialMode)
  const [tab, setTab] = useState<Tab>('field')
  const [point, setPoint] = useState<Point | null>(null)
  const [polygon, setPolygon] = useState<Point[] | null>(null)
  const [rotation, setRotation] = useState<RotationStep[]>(DEFAULT_ROTATION)
  const [waterAccess, setWaterAccess] = useState<WaterAccess>('limited')
  const [priorities, setPriorities] = useState<Priorities>({ water: 0.3, soil: 0.25, income: 0.25, erosion: 0.1, risk: 0.1 })
  const [scenario, setScenario] = useState<Scenario>({ delta_t_c: 0, precip_change_pct: 0 })
  const [details, setDetailsState] = useState<DetailsForm>(EMPTY_DETAILS)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const [report, setReport] = useState<FieldReport | null>(null)
  const [source, setSource] = useState<AnalyzeResult['source'] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const seq = useRef(0)
  const sentKey = useRef<string | null>(null) // key of the last request that produced the report on screen

  const advanced = mode === 'advanced'

  const setMode = (m: Mode) => {
    setModeState(m)
    try { localStorage.setItem('rotacast.mode', m) } catch { /* ignore */ }
    if (m === 'beginner' && tab === 'basin') setTab('field')
  }
  // "See details" on a Beginner card: switch to Advanced and open that strategy's evidence
  const openDetails = (id: string) => { setMode('advanced'); setOpenId(id) }

  // Picking a point replaces any drawn boundary; a finished boundary moves the point to its centroid so Beginner keeps the location.
  const handlePick = (p: Point) => { setPoint(p); setPolygon(null); setServerErrors({}) }
  const handlePolygon = (p: Point[] | null) => {
    setPolygon(p)
    setServerErrors({})
    if (p && p.length >= 3) { const c = centroid(p); setPoint({ lat: +c.lat.toFixed(4), lon: +c.lon.toFixed(4) }) }
  }
  const setDetails = (d: DetailsForm) => { setDetailsState(d); setServerErrors({}) }

  const clientErrors = useMemo(() => (advanced ? validateDetails(details, rotation, t) : {}), [advanced, details, rotation, t])
  const problem = advanced ? polygonProblem(polygon) : null
  const blocker = problem === 'selfx' ? t('polySelfX') : problem === 'size' ? t('polySize')
    : Object.keys(clientErrors).length ? t('fixFields') : null
  const liveArea = advanced && polygon && polygon.length >= 3 && !problem ? areaHa(polygon) : null
  const detailErrors = { ...serverErrors, ...clientErrors }

  const currentInputs = (over?: Partial<Inputs>): Inputs => ({ point, polygon, rotation, waterAccess, priorities, scenario, details, ...over })

  const run = useCallback(async (quiet: boolean, over?: Partial<Inputs>) => {
    const req = buildRequest(currentInputs(over), mode, lang)
    if (!req) return
    const my = ++seq.current
    if (!quiet) {
      setLoading(true)
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }
    setError(null)
    try {
      const res = await analyzeField(req)
      if (my !== seq.current) return
      sentKey.current = requestKey(req)
      setServerErrors({})
      setReport(res.report)
      setSource(res.source)
      if (!quiet) setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch (err) {
      if (my !== seq.current) return
      if (err instanceof ValidationError) {
        // 422: show each message next to its field; whatever does not map to a field goes near the Analyze button
        const mapped: Record<string, string> = {}
        const loose: string[] = []
        for (const it of err.issues) {
          const path = locToPath(it.loc)
          if (path) mapped[path] = mapped[path] ?? it.msg
          else loose.push(it.msg)
        }
        setServerErrors(mapped)
        setError(loose.length ? loose.join(' · ') : Object.keys(mapped).length ? t('fixFields') : t('error'))
      } else setError(t('error'))
    } finally {
      if (my === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [point, polygon, rotation, waterAccess, priorities, scenario, details, mode, lang, t])

  // Quiet re-run after a first analysis (debounced) when sliders move or the mode changes, but only if the
  // request derived from (state, mode) differs from the last one actually sent. This is what keeps a Beginner
  // result from staying scenario-adjusted (and an Advanced one from missing its polygon/details) after a switch.
  const [tick, setTick] = useState(0)
  const handled = useRef(0)
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    setTick((n) => n + 1)
  }, [priorities, scenario, mode])
  useEffect(() => {
    if (!report || loading || handled.current === tick) return
    const req = buildRequest(currentInputs(), mode, lang)
    // never send invalid inputs on a quiet re-run: the user fixes the fields and presses Analyze
    if (!req || blocker || requestKey(req) === sentKey.current) { handled.current = tick; return }
    const id = setTimeout(() => { handled.current = tick; run(true) }, 500)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, report, loading])

  const openStrategy = report?.strategies.find((s) => s.id === openId) ?? null

  return (
    <div className="min-h-screen">
      <Header lang={lang} setLang={setLang} tab={tab} setTab={setTab} mode={mode} setMode={setMode} />
      <div className="bg-sunsoft text-ink text-xs md:text-[13px] text-center px-4 py-1.5 border-b border-line">{t('supportNote')}</div>
      <main className="mx-auto max-w-[1500px] px-4 md:px-8 py-5">
        {tab === 'basin' && advanced ? <BasinView /> : (
          <div className="flex flex-col gap-8">
            <div className="mx-auto w-full max-w-[1180px] min-w-0">
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
              <InputPanel point={point} onPick={handlePick} rotation={rotation} setRotation={setRotation}
                waterAccess={waterAccess} setWaterAccess={setWaterAccess} priorities={priorities} setPriorities={setPriorities}
                scenario={scenario} setScenario={setScenario} loading={loading} error={error}
                mode={mode} polygon={polygon} onPolygon={handlePolygon} areaHa={liveArea}
                details={details} setDetails={setDetails} detailErrors={detailErrors} blocker={blocker}
                onAnalyze={() => run(false)}
                onDemo={() => { setPoint(KONYA); setPolygon(null); run(false, { point: KONYA, polygon: null }) }} />
            </div>
            <div ref={resultsRef} className="flex flex-col gap-6 min-w-0 scroll-mt-4">
              {loading ? <div className="mx-auto w-full max-w-2xl"><Loading /></div> : !report ? null : (
                <>
                  {source && source !== 'live' && (
                    <div role="status" className="rounded-xl bg-sunsoft border border-sun px-4 py-2 text-sm">
                      {t(source === 'mock-forced' ? 'mockForced' : 'mockBanner')} {advanced ? t('scenarioMock') : ''}
                    </div>
                  )}
                  <div className="text-xs text-muted break-words">
                    📍 {report.location.label} · {Math.round(report.location.elevation_m)} m
                    {report.location.area_ha !== undefined && <> · {t('polyArea')}: {fmt(report.location.area_ha, report.location.area_ha < 10 ? 2 : 1, lang)} {t('polyHa')}</>}
                  </div>
                  {advanced ? (
                    <>
                      <UserInputs report={report} />
                      <Strategies strategies={report.strategies} onOpen={setOpenId} areaHa={report.location.area_ha} />
                      <FieldMemory fm={report.field_memory} />
                      <ClimateShift climate={report.climate} />
                    </>
                  ) : (
                    <>
                      <SimpleResults strategies={report.strategies} onDetails={openDetails} />
                      <AboutField report={report} />
                    </>
                  )}
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
