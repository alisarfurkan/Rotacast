import { useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { getBasin } from '../api'
import type { BasinReport } from '../types'
import { Chart, useCssVar, type EOption } from './Chart'
import { style as mapStyle } from './FieldPicker'
import { useLang, useT } from '../ctx'
import { fmt, pick, signed } from '../util'

const ARCH = [
  { id: 'water_saver', icon: '💧', color: '#1f6a93' },
  { id: 'soil_builder', icon: '🌱', color: '#4f8a35' },
  { id: 'balanced_income', icon: '⚖️', color: '#c98a12' },
]
const ARCH_COLOR: Record<string, string> = Object.fromEntries(ARCH.map((a) => [a.id, a.color]))

function mix(a: number[], b: number[], t: number) {
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`
}

function Seg<T extends string | number>({ label, value, opts, onChange }: {
  label: string; value: T; opts: { v: T; text: string }[]; onChange: (v: T) => void
}) {
  return (
    <fieldset>
      <legend className="text-xs font-bold uppercase tracking-wider text-muted mb-1.5">{label}</legend>
      <div className="flex gap-1 flex-wrap">
        {opts.map((o) => (
          <button key={String(o.v)} onClick={() => onChange(o.v)} aria-pressed={value === o.v}
            className={'rounded-lg px-3 py-2 text-sm font-semibold border transition ' + (value === o.v ? 'bg-soil text-bg border-soil' : 'border-line bg-surface hover:bg-surface2')}>
            {o.text}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export function BasinView() {
  const t = useT()
  const lang = useLang()
  const muted = useCssVar('--muted')
  const [data, setData] = useState<{ report: BasinReport; mock: boolean } | null>(null)
  const [rate, setRate] = useState(0.1)
  const [arch, setArch] = useState('water_saver')
  const [horizon, setHorizon] = useState(10)
  const [colorBy, setColorBy] = useState<'change' | 'best'>('change')

  useEffect(() => { getBasin().then(setData) }, [])
  const rep = data?.report
  const sc = rep?.scenarios?.[arch]?.[String(rate)]?.[String(horizon)]

  const graceOpt: EOption | null = useMemo(() => {
    const g = rep?.grace
    if (!g || !g.available || !g.series?.length || g.trend_cm_yr == null) return null
    const pts = g.series.map((p) => [p.date, p.tws_cm] as [string, number])
    const ts = g.series.map((p) => new Date(p.date).getTime())
    const yr = 365.25 * 86400000
    const tm = ts.reduce((a, b) => a + b, 0) / ts.length
    const ym = g.series.reduce((a, b) => a + b.tws_cm, 0) / g.series.length
    const trend = [ts[0], ts[ts.length - 1]].map((x) => [new Date(x).toISOString().slice(0, 10), ym + g.trend_cm_yr! * ((x - tm) / yr)])
    return {
      animation: false,
      grid: { left: 40, right: 12, top: 14, bottom: 26 },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => (+v).toFixed(1) + ' cm' },
      xAxis: { type: 'time', axisLabel: { color: muted, fontSize: 10 } },
      yAxis: { type: 'value', name: 'cm', nameTextStyle: { color: muted, fontSize: 10 }, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(120,100,70,.18)' } } },
      series: [
        { name: 'GRACE', type: 'line', showSymbol: false, data: pts, lineStyle: { width: 1.5, color: '#1f6a93' }, areaStyle: { color: 'rgba(31,106,147,.12)' } },
        { name: 'Trend', type: 'line', showSymbol: false, data: trend, lineStyle: { width: 3, color: '#b23a2a', type: 'dashed' } },
      ],
    }
  }, [rep, muted])

  const lossOpt: EOption | null = useMemo(() => {
    const loss = rep?.grace?.loss_mm3_yr
    if (!sc || loss == null) return null
    return {
      animation: true,
      grid: { left: 130, right: 40, top: 6, bottom: 22 },
      tooltip: { valueFormatter: (v: number) => fmt(v, 0, lang) + ' Mm³/yr' },
      xAxis: { type: 'value', axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(120,100,70,.18)' } } },
      yAxis: { type: 'category', inverse: true, data: [t('bsLoss'), t('bsSave')], axisLabel: { color: muted, fontSize: 11, width: 120, overflow: 'break' } },
      series: [{ type: 'bar', barWidth: 26, label: { show: true, position: 'right', color: muted, fontSize: 11, formatter: (p: { value: number }) => fmt(p.value, 0, lang) },
        data: [{ value: +loss.toFixed(0), itemStyle: { color: '#b23a2a' } }, { value: +(-sc.irrigation_change_mm3_yr.p50).toFixed(0), itemStyle: { color: '#1f6a93' } }] }],
    }
  }, [rep, sc, muted, lang]) // eslint-disable-line react-hooks/exhaustive-deps

  const prodOpt: EOption | null = useMemo(() => {
    if (!sc) return null
    const rows = sc.production_change_t_yr.slice(0, 10).sort((a, b) => a.change_t_yr - b.change_t_yr)
    return {
      animation: true,
      grid: { left: 112, right: 50, top: 6, bottom: 22 },
      tooltip: { valueFormatter: (v: number) => signed(v, 0, lang) + ' ' + t('bsProdUnit') },
      xAxis: { type: 'value', axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(120,100,70,.18)' } } },
      yAxis: { type: 'category', data: rows.map((r) => pick(r.name, lang)), axisLabel: { color: muted, fontSize: 11, width: 104, overflow: 'truncate' }, axisTick: { show: false } },
      series: [{ type: 'bar', barMaxWidth: 18, label: { show: true, color: muted, fontSize: 10, position: 'right', formatter: (p: { value: number }) => signed(p.value, 0, lang) },
        data: rows.map((r) => ({ value: Math.round(r.change_t_yr / 1000), itemStyle: { color: r.change_t_yr >= 0 ? '#4f8a35' : '#a8622a' } })) }],
    }
  }, [sc, muted, lang]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!rep) return <p className="card p-8 text-center mt-6" role="status">{t('bsLoading')}</p>

  const saved = sc ? -sc.irrigation_change_mm3_yr.p50 : 0
  const sLo = sc ? -sc.irrigation_change_mm3_yr.p90 : 0
  const sHi = sc ? -sc.irrigation_change_mm3_yr.p10 : 0
  const off = sc?.grace_offset_pct
  const g = rep.grace
  const capPct = Math.round(Number(rep.assumptions.find((a) => a.id === 'max_production_increase')?.value ?? 0.25) * 100)
  const flagText = (fl: { crop_id: string }[]) => t('bsMarketFlag', {
    crops: fl.map((f) => pick(sc?.production_change_t_yr.find((p) => p.crop_id === f.crop_id)?.name ?? { en: f.crop_id, tr: f.crop_id }, lang)).join(', '), cap: capPct })
  const hl = rep.headline
  const bandText = (a: number, b: number) => t('bsRange', { a: fmt(Math.min(a, b), 0, lang), b: fmt(Math.max(a, b), 0, lang) })

  return (
    <div className="flex flex-col gap-6 mt-2 rise">
      <div role="note" className="rounded-2xl border-2 border-sun bg-sunsoft px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="font-display text-xl font-extrabold text-sun">⚠ {t('bsBanner')}</span>
        <span className="text-sm">{pick(rep.scenario_notice, lang)} {t('bsOrder')}</span>
      </div>

      <section className="card p-4 md:p-6" aria-labelledby="bs-title">
        <h2 id="bs-title" className="font-display text-2xl md:text-3xl font-extrabold text-soil">{t('bsTitle')} · {pick(rep.region.name, lang)}</h2>
        <p className="text-sm text-muted mb-1">{t('bsSub')}</p>
        <p className="text-xs rounded-lg bg-surface2 px-3 py-2 mb-2">ⓘ {t('bsCardsNote')}</p>
        <p className="text-xs text-muted mb-4">{t('bsCells', { n: rep.totals.n_cells, ha: fmt(rep.totals.cropland_ha, 0, lang), irr: fmt(rep.totals.irrigated_ha, 0, lang) })}</p>
        {data?.mock && <p className="text-xs text-sun mb-3">{t('bsMock')}</p>}

        <div className="grid gap-4 md:grid-cols-3 mb-5">
          <Seg label={t('bsAdopt')} value={rate} onChange={setRate} opts={rep.adoption_rates.map((r) => ({ v: r, text: Math.round(r * 100) + '%' }))} />
          <Seg label={t('bsArch')} value={arch} onChange={setArch}
            opts={ARCH.map((a) => ({ v: a.id, text: a.icon + ' ' + pick(rep.strategies.find((s) => s.id === a.id)?.name, lang) }))} />
          <Seg label={t('bsHorizon')} value={horizon} onChange={setHorizon}
            opts={rep.horizons.map((h) => ({ v: h, text: t(h >= 10 ? 'bsH10' : 'bsH5') }))} />
        </div>

        {hl && hl.scenarios.length > 0 && (
          <div className="rounded-2xl border border-line bg-surface2 p-4 mb-5" aria-labelledby="hl-title">
            <h3 id="hl-title" className="font-display text-lg font-extrabold text-soil">{t('bsHeadline')} · <span className="text-sm font-semibold text-muted">{t('bsHeadlineSub', { p: Math.round(hl.adoption * 100) })}</span></h3>
            <div className="grid gap-3 md:grid-cols-3 mt-2">
              {hl.scenarios.map((h) => (
                <div key={h.archetype} className="rounded-xl bg-surface p-3 text-sm" style={{ borderLeft: `4px solid ${ARCH_COLOR[h.archetype] ?? '#888'}` }}>
                  <div className="font-bold">{pick(h.name, lang)}</div>
                  <div className="text-xs text-muted mt-1">{t('bsHlSaved')}: <b className="text-water">{bandText(-h.water_change_mm3_yr.p90, -h.water_change_mm3_yr.p10)}</b> Mm³/yr</div>
                  {h.grace_offset_pct && <div className="text-xs text-muted">{t('bsHlOffset')}: <b className="text-leaf">{bandText(h.grace_offset_pct.p10, h.grace_offset_pct.p90)} %</b></div>}
                  <div className={'text-xs font-bold mt-1 ' + (h.market_plausible ? 'text-leaf' : 'text-sun')}>{h.market_plausible ? '✓ ' + t('bsMarketOk') : '⚠ ' + t('bsMarketWarn')}</div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted mt-2">{pick(hl.note, lang)}</p>
          </div>
        )}

        {sc && sc.market_flags && sc.market_flags.length > 0 && (
          <div role="alert" className="rounded-xl border border-sun bg-sunsoft px-3 py-2 text-sm mb-4">⚠ {flagText(sc.market_flags)}</div>
        )}

        {sc ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl p-5" style={{ background: 'var(--water-soft)' }} aria-live="polite">
              <div className="text-xs font-bold uppercase tracking-wider text-water">💧 {t('bsSaved')}</div>
              <div className="font-display text-6xl font-black text-water tabular-nums leading-none my-2">{fmt(saved, 0, lang)}</div>
              <div className="text-sm font-semibold text-water">{t('bsSavedUnit')}</div>
              <div className="text-xs text-muted mt-1">{bandText(sLo, sHi)}</div>
            </div>
            <div className="rounded-2xl p-5" style={{ background: 'var(--leaf-soft)' }} aria-live="polite">
              <div className="text-xs font-bold uppercase tracking-wider text-leaf">🛰 NASA GRACE</div>
              {off ? (
                <>
                  <div className="font-display text-6xl font-black text-leaf tabular-nums leading-none my-2">{fmt(off.p50, 0, lang)}%</div>
                  <div className="text-sm font-semibold text-ink leading-snug">{t('bsOffset')}</div>
                  <div className="text-xs text-muted mt-1">{bandText(off.p10, off.p90).replace(/(\d)(?=\D*$)/, '$1%')}</div>
                  {off.p50 >= 50 && <div className="text-xs font-bold text-sun mt-2">⚠ {t('bsOffsetBig')}</div>}
                </>
              ) : <p className="text-sm text-muted mt-2">{t('bsGraceNA')}</p>}
            </div>
          </div>
        ) : null}
      </section>

      <section className="card p-4 md:p-6" aria-labelledby="gr-title">
        <h2 id="gr-title" className="font-display text-2xl font-extrabold text-soil">🛰 {t('bsGrace')}</h2>
        {graceOpt && g.trend_cm_yr != null ? (
          <div className="grid md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-5 mt-1">
            <div>
              <p className="text-xs text-muted mb-1">{t('bsGraceSub')}</p>
              <Chart option={graceOpt} height={250} label={t('bsGrace')} />
              <p className="text-sm font-semibold text-bad mt-1">
                {t('bsTrend', { v: fmt(g.trend_cm_yr, 2, lang), a: fmt(g.trend_ci95_cm_yr?.[0] ?? 0, 2, lang), b: fmt(g.trend_ci95_cm_yr?.[1] ?? 0, 2, lang) })}
              </p>
              {g.volume_change_mm3_yr != null && (
                <p className="text-sm text-muted">
                  {t('bsVolume', { v: fmt(g.volume_change_mm3_yr, 0, lang), a: fmt(g.volume_change_ci95_mm3_yr?.[0] ?? 0, 0, lang), b: fmt(g.volume_change_ci95_mm3_yr?.[1] ?? 0, 0, lang) })}
                </p>
              )}
              <p className="text-xs text-muted mt-1">{pick(g.note, lang)}</p>
            </div>
            <div>
              <h3 className="text-sm font-bold mb-1">{t('bsLossVsSave')}</h3>
              {lossOpt && <Chart option={lossOpt} height={130} label={t('bsLossVsSave')} />}
              <p className="text-[11px] text-muted">Mm³/yr</p>
            </div>
          </div>
        ) : <p className="text-sm text-muted mt-2">{t('bsGraceNA')}</p>}
      </section>

      <section className="card p-4 md:p-6" aria-labelledby="mp-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="mp-title" className="font-display text-2xl font-extrabold text-soil">{t('bsMap')}</h2>
          <div className="flex gap-1" role="group">
            {(['change', 'best'] as const).map((m) => (
              <button key={m} onClick={() => setColorBy(m)} aria-pressed={colorBy === m}
                className={'rounded-lg px-3 py-1 text-xs font-semibold border ' + (colorBy === m ? 'bg-soil text-bg border-soil' : 'border-line hover:bg-surface2')}>
                {t(m === 'change' ? 'bsColorChange' : 'bsColorBest')}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-muted mb-2">{t('bsMapHint')}</p>
        <BasinMap rep={rep} arch={arch} colorBy={colorBy} />
        <div className="flex flex-wrap gap-3 text-xs text-muted mt-2">
          {colorBy === 'best'
            ? ARCH.map((a) => <span key={a.id} className="flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm" style={{ background: a.color }} />{a.icon} {pick(rep.strategies.find((s) => s.id === a.id)?.name, lang)}</span>)
            : <span className="flex items-center gap-2"><i className="inline-block w-28 h-2.5 rounded" style={{ background: 'linear-gradient(90deg,#e9f1f5,#1f6a93)' }} />{t('bsColorChange')}: 0 → max</span>}
        </div>
      </section>

      {prodOpt && (
        <section className="card p-4 md:p-6" aria-labelledby="pr-title">
          <h2 id="pr-title" className="font-display text-2xl font-extrabold text-soil">{t('bsProd')}</h2>
          <p className="text-xs text-muted mb-1">{t('bsProdSub')} ({t('bsProdUnit')})</p>
          <Chart option={prodOpt} height={320} label={t('bsProd')} />
        </section>
      )}

      <section className="card p-4 md:p-6 flex flex-col gap-3">
        <details>
          <summary className="cursor-pointer font-display text-lg font-extrabold">{t('bsAssump')} ({rep.assumptions.length})</summary>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm">
            {rep.assumptions.map((a) => (
              <li key={a.id}><b>{pick(a.label, lang)}:</b> <span className="tabular-nums">{typeof a.value === 'object' ? JSON.stringify(a.value) : String(a.value)}</span>
                <span className="text-muted text-xs"> — {a.source}</span></li>
            ))}
          </ul>
        </details>
        <details open>
          <summary className="cursor-pointer font-display text-lg font-extrabold">{t('bsLimits')} ({rep.limitations.length})</summary>
          <ul className="mt-2 list-disc pl-5 flex flex-col gap-1.5 text-sm">
            {rep.limitations.map((l, i) => <li key={i}>{pick(l, lang)}</li>)}
          </ul>
        </details>
        <div>
          <h3 className="font-display text-lg font-extrabold mb-1">{t('bsSources')}</h3>
          <div className="flex flex-wrap gap-2">
            {rep.sources.map((s) => (
              <a key={s.id} href={s.url} target="_blank" rel="noreferrer" className="rounded-full bg-watersoft text-water text-xs font-semibold px-2.5 py-1">{s.name} ↗</a>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

function BasinMap({ rep, arch, colorBy }: { rep: BasinReport; arch: string; colorBy: 'change' | 'best' }) {
  const t = useT()
  const lang = useLang()
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)
  const popup = useRef<maplibregl.Popup | null>(null)
  const langRef = useRef({ t, lang })
  langRef.current = { t, lang }

  const geo = useMemo(() => {
    const ch = rep.cells.map((c) => c.strategies[arch]?.water_change_m3_ha_p50 ?? 0)
    const max = Math.max(1, ...ch.map((v) => Math.abs(v)))
    return {
      type: 'FeatureCollection' as const,
      features: rep.cells.map((c, i) => {
        const [x0, y0, x1, y1] = c.clip ?? c.bounds
        const color = colorBy === 'best' ? (ARCH_COLOR[c.best_strategy.archetype] ?? '#888')
          : ch[i] <= 0 ? mix([233, 241, 245], [31, 106, 147], Math.min(1, -ch[i] / max)) : mix([245, 225, 215], [178, 58, 42], Math.min(1, ch[i] / max))
        return {
          type: 'Feature' as const,
          properties: { color, change: Math.round(ch[i]), bestEn: c.best_strategy.name.en, bestTr: c.best_strategy.name.tr },
          geometry: { type: 'Polygon' as const, coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]] },
        }
      }),
    }
  }, [rep, arch, colorBy])
  const geoRef = useRef(geo)
  geoRef.current = geo

  useEffect(() => {
    if (!el.current) return
    const [w, s, e, n] = rep.region.bbox
    const m = new maplibregl.Map({ container: el.current, style: mapStyle, bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: 24 }, attributionControl: { compact: true } })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => {
      m.addSource('cells', { type: 'geojson', data: geoRef.current })
      m.addLayer({ id: 'cells-fill', type: 'fill', source: 'cells', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.72 } })
      m.addLayer({ id: 'cells-line', type: 'line', source: 'cells', paint: { 'line-color': '#ffffff', 'line-width': 0.8, 'line-opacity': 0.6 } })
      m.addSource('bbox', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } } })
      m.addLayer({ id: 'bbox-line', type: 'line', source: 'bbox', paint: { 'line-color': '#f2c14e', 'line-width': 2.5, 'line-dasharray': [3, 2] } })
      ready.current = true
    })
    popup.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false })
    m.on('mousemove', 'cells-fill', (ev) => {
      const f = ev.features?.[0]
      if (!f) return
      const { t: tt, lang: lg } = langRef.current
      const p = f.properties as { change: number; bestEn: string; bestTr: string }
      m.getCanvas().style.cursor = 'pointer'
      popup.current!.setLngLat(ev.lngLat).setHTML(
        `<div style="color:#2b1f16;font:600 12px Inter,sans-serif">${tt('bsCellChange', { v: signed(p.change, 0, lg) })}<br/>${tt('bsCellBest', { n: lg === 'tr' ? p.bestTr : p.bestEn })}</div>`).addTo(m)
    })
    m.on('mouseleave', 'cells-fill', () => { m.getCanvas().style.cursor = ''; popup.current?.remove() })
    map.current = m
    return () => { ready.current = false; m.remove(); map.current = null }
  }, [rep])

  useEffect(() => {
    const src = map.current?.getSource('cells') as maplibregl.GeoJSONSource | undefined
    if (ready.current && src) src.setData(geo)
  }, [geo])

  return <div ref={el} className="h-80 md:h-[420px] w-full rounded-2xl overflow-hidden border border-line" aria-label={t('bsMap')} />
}
