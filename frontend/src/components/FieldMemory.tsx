import { useMemo } from 'react'
import type { FieldMemory as FM } from '../types'
import { Chart, useCssVar, type EOption } from './Chart'
import { Term } from './Term'
import { useLang, useT } from '../ctx'
import { doyToMonthDay, fmt, fuzzyDoy, monthNames } from '../util'
import { STRINGS, type Key } from '../i18n'

const BIN = 8
const NB = Math.ceil(366 / BIN)

export function FieldMemory({ fm }: { fm: FM }) {
  const t = useT()
  if (!fm.years?.length || !fm.ndvi?.length) {
    return (
      <section className="card p-5 md:p-6 rise">
        <h2 className="font-display text-2xl md:text-3xl font-extrabold text-soil mb-2">{t('fmTitle')}</h2>
        <p className="rounded-xl bg-surface2 px-4 py-3 text-sm">ⓘ {t('fmUnavailable')}</p>
      </section>
    )
  }
  return <FieldMemoryChart fm={fm} />
}

function FieldMemoryChart({ fm }: { fm: FM }) {
  const t = useT()
  const lang = useLang()
  const muted = useCssVar('--muted')
  const bad = useCssVar('--bad')

  const { heat, years, labels } = useMemo(() => {
    const ys = fm.years.map((y) => y.year)
    const sums: Record<number, { s: number; n: number }[]> = {}
    for (const y of ys) sums[y] = Array.from({ length: NB }, () => ({ s: 0, n: 0 }))
    for (const p of fm.ndvi) {
      const d = new Date(p.date + 'T00:00:00Z')
      const y = d.getUTCFullYear()
      const doy = Math.floor((d.getTime() - Date.UTC(y, 0, 0)) / 86400000)
      const b = Math.min(NB - 1, Math.floor((doy - 1) / BIN))
      if (sums[y]) { sums[y][b].s += p.ndvi_smooth; sums[y][b].n++ }
    }
    const data: [number, number, number][] = []
    ys.forEach((y, yi) => sums[y].forEach((c, bi) => { if (c.n) data.push([bi, yi, +(c.s / c.n).toFixed(3)]) }))
    // month labels at first bin containing a month start
    const mn = monthNames(lang)
    const starts = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    const lb = Array.from({ length: NB }, () => '')
    starts.forEach((sd, m) => { const bi = Math.floor((sd - 1) / BIN); if (!lb[bi]) lb[bi] = mn[m] })
    return { heat: data, years: ys, labels: lb }
  }, [fm, lang])

  const stress = new Set(fm.stress_years)
  const bareArea = fm.bare_windows.filter((w) => w.end_doy >= w.start_doy).map((w) => [
    { xAxis: Math.floor((w.start_doy - 1) / BIN), itemStyle: { color: 'rgba(0,0,0,0)', borderColor: '#f2c14e', borderWidth: 2, borderType: 'dashed' } },
    { xAxis: Math.min(NB - 1, Math.floor((w.end_doy - 1) / BIN)) },
  ])

  const heatOpt: EOption = useMemo(() => ({
    animation: false,
    grid: { left: 58, right: 12, top: 8, bottom: 30 },
    tooltip: {
      formatter: (p: { data: [number, number, number] }) => {
        const [b, yi, v] = p.data
        return `${years[yi]} · ${doyToMonthDay(b * BIN + 1, lang)}<br/>NDVI <b>${v.toFixed(2)}</b>`
      },
    },
    xAxis: { type: 'category', data: labels.map((_, i) => 'b' + i), splitArea: { show: false },
      axisLabel: { interval: 0, color: muted, fontSize: 10, formatter: (_v: string, i: number) => labels[i] },
      axisTick: { show: false }, axisLine: { show: false } },
    yAxis: { type: 'category', data: years, inverse: true, axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { interval: 0, fontSize: 9, color: muted, rich: { s: { color: bad, fontWeight: 'bold', fontSize: 10 } },
        formatter: (v: string) => (stress.has(+v) ? `{s|${v} ▲}` : (+v) % 5 === 0 ? v : '') } },
    visualMap: { show: false, min: 0.1, max: 0.65, inRange: { color: ['#6b4a2b', '#a98457', '#d9c78a', '#9fc66b', '#3f8a32', '#1d5a22'] } },
    series: [{ type: 'heatmap', data: heat, itemStyle: { borderColor: 'rgba(0,0,0,0)', borderWidth: 0.5 },
      markArea: { silent: true, data: bareArea } }],
  }), [heat, years, labels, muted, bad, lang, fm]) // eslint-disable-line react-hooks/exhaustive-deps

  const lineOpt: EOption = useMemo(() => ({
    animation: false,
    grid: { left: 36, right: 12, top: 14, bottom: 26 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'time', axisLabel: { color: muted, fontSize: 10 }, axisLine: { lineStyle: { color: muted } } },
    yAxis: { type: 'value', min: 0, max: 0.8, splitNumber: 4, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(120,100,70,.18)' } } },
    series: [
      { name: 'NDVI', type: 'scatter', symbolSize: 3, itemStyle: { color: 'rgba(120,100,70,.45)' }, data: fm.ndvi.map((p) => [p.date, p.ndvi]), z: 1 },
      { name: 'NDVI smooth', type: 'line', showSymbol: false, lineStyle: { width: 1.6, color: '#3f8a32' }, data: fm.ndvi.map((p) => [p.date, p.ndvi_smooth]), z: 2,
        markArea: { silent: true, itemStyle: { color: 'rgba(178,58,42,.22)' },
          data: fm.stress_years.map((y) => [{ xAxis: `${y}-01-01` }, { xAxis: `${y}-12-31` }]) } },
    ],
  }), [fm, muted])

  // plain-language takeaway
  const med = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)] ?? 0 }
  const counts: Record<string, number> = {}
  fm.years.forEach((y) => { counts[y.pattern] = (counts[y.pattern] || 0) + 1 })
  const majority = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'winter_crop'
  const mj = fm.years.filter((y) => y.pattern === majority)
  const gu = med(mj.map((y) => y.greenup_doy).filter((d) => d > 0)), pk = med(mj.map((y) => y.peak_doy))
  const typPeak = med(mj.map((y) => y.peak_ndvi))
  // merge a window that ends at year end with one that starts at day 1
  const ws = fm.bare_windows.map((w) => ({ from: w.start_doy, to: w.end_doy, len: w.end_doy - w.start_doy + 1 }))
  const first = ws.find((w) => w.from <= 1), last = ws.find((w) => w.to >= 364)
  let wins = ws
  if (first && last && first !== last) {
    wins = ws.filter((w) => w !== first && w !== last)
    wins.push({ from: last.from, to: first.to, len: last.len + first.len })
  }
  const main = [...wins].sort((a, b) => b.len - a.len)[0]
  const takeBare = main
    ? t('takeBare', { from: fuzzyDoy(main.from, lang), to: fuzzyDoy(main.to, lang) })
    : t('takeNoBare')
  const bareDays = main ? main.len : 0
  const patKey = ('takeP_' + majority) as Key
  const patText = patKey in STRINGS.en
    ? t(patKey, { gu: doyToMonthDay(gu, lang), pk: doyToMonthDay(pk, lang), n: counts[majority], total: fm.years.length })
    : ''

  return (
    <section className="card p-4 md:p-6 rise" aria-labelledby="fm-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="fm-title" className="font-display text-2xl md:text-3xl font-extrabold text-soil">{t('fmTitle')}</h2>
        <span className="text-xs text-muted">{t('fmSub')} · <Term k="ndvi" /></span>
      </div>
      <p className="font-display text-lg md:text-xl leading-snug mt-2 mb-4 rounded-xl bg-sunsoft text-ink px-4 py-3 border-l-4 border-sun">
        {takeBare}
      </p>

      <div className="grid md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-5">
        <div>
          <h3 className="text-sm font-bold mb-0.5">{t('fmHeat')}</h3>
          <p className="text-xs text-muted mb-1">{t('fmHeatHint')}</p>
          <Chart option={heatOpt} height={400} label={t('fmHeat')} />
          <div className="flex flex-wrap gap-4 text-xs text-muted mt-1">
            <span className="flex items-center gap-1.5"><i className="inline-block w-4 h-3 border-2 border-dashed" style={{ borderColor: '#f2c14e' }} />{t('fmLegendBare')}</span>
            <span className="flex items-center gap-1.5"><b className="text-bad">▲</b><Term k="stress">{t('fmLegendStress')}</Term></span>
            <span className="flex items-center gap-1.5">
              <i className="inline-block w-24 h-2.5 rounded" style={{ background: 'linear-gradient(90deg,#6b4a2b,#a98457,#d9c78a,#9fc66b,#3f8a32,#1d5a22)' }} />
              <span>0.1 → 0.65</span>
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-2">
            <Stat label={t('peakNdvi')} value={fmt(typPeak, 2, lang)} />
            <Stat label={t('greenup')} value={doyToMonthDay(gu, lang)} />
            <Stat label={t('stressCount')} value={String(fm.stress_years.length)} tone="bad" />
            <Stat label={t('bareDays')} value={String(bareDays)} tone="sun" />
          </div>
          <p className="text-sm text-muted">
            {patText}{' '}
            {fm.stress_years.length > 0 && <>{t('takeStress', { years: fm.stress_years.join(', ') })} <Term k="stress">ⓘ</Term></>}
          </p>
          <div>
            <h3 className="text-sm font-bold mb-1">{t('fmLine')}</h3>
            <Chart option={lineOpt} height={190} label={t('fmLine')} />
          </div>
        </div>
      </div>
    </section>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'bad' | 'sun' }) {
  const c = tone === 'bad' ? 'text-bad' : tone === 'sun' ? 'text-sun' : 'text-leaf'
  return (
    <div className="rounded-xl bg-surface2 px-3 py-2.5">
      <div className={'font-display text-2xl font-extrabold tabular-nums ' + c}>{value}</div>
      <div className="text-[11px] text-muted leading-tight">{label}</div>
    </div>
  )
}
