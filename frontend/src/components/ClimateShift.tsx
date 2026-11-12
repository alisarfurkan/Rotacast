import { useMemo } from 'react'
import type { Climate, ShiftMetric } from '../types'
import { Chart, useCssVar, type EOption } from './Chart'
import { Term } from './Term'
import { useLang, useT } from '../ctx'
import { doyToMonthDay, fmt, monthNames, pick, unitLabel } from '../util'

// Which direction of change is adverse for a farmer (+1: increase is bad, -1: decrease is bad, 0: neutral).
const ADVERSE: Record<string, number> = { precip_mm: -1, annual_precip: -1, spring_precip_mm: -1, et0_mm: 1, annual_et0: 1, water_deficit: 1, tmean_c: 1, tmean: 1, summer_tmax_c: 1, heat_days_35: 1, gdd0: 0, last_spring_frost: 0, first_fall_frost: 0, frost_free_days: 0 }

function MetricCard({ m }: { m: ShiftMetric }) {
  const t = useT()
  const lang = useLang()
  const isDoy = m.unit === 'doy'
  const unit = isDoy ? '' : unitLabel(m.unit, lang)
  const up = m.delta > 0
  const adv = ADVERSE[m.id] ?? 0
  const tone = Math.abs(m.delta) < 1e-9 ? 'muted' : adv === 0 ? 'sun' : (adv > 0) === up ? 'bad' : 'leaf'
  const nDec = Math.abs(m.delta) < 10 ? 1 : 0
  const text = isDoy
    ? (Math.abs(m.delta) < 0.5 ? t('unchanged') : t(up ? 'later' : 'earlier', { n: fmt(Math.abs(m.delta), 0, lang) }))
    : Math.abs(m.delta) < 1e-9 ? t('unchanged') : t(up ? 'moreOf' : 'lessOf', { n: `${fmt(Math.abs(m.delta), nDec, lang)} ${unit}` })
  const show = (v: number) => (isDoy ? doyToMonthDay(v, lang) : `${fmt(v, nDec, lang)} ${unit}`)
  const label = pick(m.label, lang)
  const body = (m.id === 'annual_et0' || m.id === 'et0_mm') ? <Term k="et0">{label}</Term> : m.id === 'water_deficit' ? <Term k="deficit">{label}</Term> : label
  return (
    <div className="rounded-2xl border border-line bg-surface2 p-3.5">
      <div className="text-xs font-semibold text-muted leading-tight min-h-8">{body}</div>
      <div className="mt-1.5 flex items-center gap-2">
        <span className={'text-3xl font-black leading-none text-' + tone} aria-hidden>{Math.abs(m.delta) < 1e-9 ? '→' : up ? '↑' : '↓'}</span>
        <span className={'font-display text-lg font-extrabold leading-tight text-' + tone}>{text}</span>
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-muted tabular-nums">
        <span>{t('csEarly')}: <b className="text-ink">{show(m.early)}</b></span>
        <span>{t('csRecent')}: <b className="text-ink">{show(m.late)}</b></span>
      </div>
      <div className="text-[10.5px] text-muted mt-1">
        {m.p_value < 0.1 ? '● ' + t('significant') : '○ ' + t('notSignificant')}
      </div>
    </div>
  )
}

export function ClimateShift({ climate }: { climate: Climate }) {
  const t = useT()
  const lang = useLang()
  const muted = useCssVar('--muted')
  const ink = useCssVar('--ink')
  const rain = climate.annual.reduce((s, r) => s + r.precip_mm, 0) / climate.annual.length
  const et0 = climate.annual.reduce((s, r) => s + r.et0_mm, 0) / climate.annual.length

  const opt: EOption = useMemo(() => ({
    animation: false,
    grid: { left: 40, right: 12, top: 34, bottom: 26 },
    legend: { top: 0, textStyle: { color: ink, fontSize: 11 }, itemWidth: 12, itemHeight: 10 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => v + ' mm' },
    xAxis: { type: 'category', data: monthNames(lang), axisLabel: { color: muted, fontSize: 10 }, axisTick: { show: false } },
    yAxis: { type: 'value', name: 'mm', nameTextStyle: { color: muted, fontSize: 10 }, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(120,100,70,.18)' } } },
    series: [
      { name: t('csRain'), type: 'bar', data: climate.monthly_normals.map((m) => m.precip_mm), itemStyle: { color: '#1f6a93', borderRadius: [4, 4, 0, 0] } },
      { name: t('csEt0'), type: 'bar', data: climate.monthly_normals.map((m) => m.et0_mm), itemStyle: { color: '#d99a2b', borderRadius: [4, 4, 0, 0] } },
    ],
  }), [climate, lang, muted, ink]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="card p-4 md:p-6 rise" aria-labelledby="cs-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
        <h2 id="cs-title" className="font-display text-2xl md:text-3xl font-extrabold text-soil">{t('csTitle')}</h2>
        <span className="text-xs text-muted">
          {t('csSub', { a: `${climate.shift.early[0]}–${climate.shift.early[1]}`, b: `${climate.shift.late[0]}–${climate.shift.late[1]}` })}
        </span>
      </div>
      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {climate.shift.metrics.map((m) => <MetricCard key={m.id} m={m} />)}
      </div>
      <div className="mt-5 grid md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-5 items-center">
        <div>
          <h3 className="text-sm font-bold mb-1">{t('csMonthly')}</h3>
          <Chart option={opt} height={240} label={t('csMonthly')} />
        </div>
        <div className="rounded-2xl bg-watersoft p-5">
          <div className="text-xs font-bold uppercase tracking-wider text-water"><Term k="deficit">{t('csDeficit')}</Term></div>
          <div className="font-display text-5xl font-black text-water tabular-nums my-1">
            {fmt(climate.water_balance.annual_deficit_mm, 0, lang)}<span className="text-xl font-bold"> mm</span>
          </div>
          <p className="text-sm text-ink leading-snug">
            {t('csDeficitText', { et0: fmt(et0, 0, lang), rain: fmt(rain, 0, lang), gap: fmt(et0 - rain, 0, lang) })}
          </p>
        </div>
      </div>
    </section>
  )
}
