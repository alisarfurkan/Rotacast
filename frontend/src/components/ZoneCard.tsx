import type { ZoneInfo, ZoneStation } from '../types'
import { Term } from './Term'
import { useLang, useT } from '../ctx'
import { fmt, pick } from '../util'

const POS = { low: 'posLow', mid: 'posMid', high: 'posHigh' } as const

function Stat({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm font-semibold">{children}</div>
    </div>
  )
}

function Station({ s }: { s: ZoneStation }) {
  const t = useT()
  const lang = useLang()
  const n = s.nasa_power
  const f = (v: number, d = 1) => fmt(v, d, lang)
  return (
    <li className="rounded-xl border border-line bg-surface2 p-3.5">
      <div className="font-semibold mb-2">{s.name} <span className="text-xs font-normal text-muted">({s.period})</span></div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-4 gap-y-2.5">
        {s.erinc && (
          <Stat label={<Term k="erinc">{t('zoneErinc')}</Term>}>
            {f(s.erinc.index)} <span className="font-normal text-muted">{s.erinc.type}</span>
          </Stat>
        )}
        {s.aydeniz && <Stat label={<Term k="aydeniz">{t('zoneAydeniz')}</Term>}>{s.aydeniz.type}</Stat>}
        {s.thornthwaite && <Stat label={<Term k="thornthwaite">{t('zoneThornthwaite')}</Term>}>{s.thornthwaite.class}</Stat>}
        {s.trewartha_winter && <Stat label={t('zoneWinter')}>{f(s.trewartha_winter.mean_temp_c)} °C</Stat>}
        {s.trewartha_summer && <Stat label={t('zoneSummer')}>{f(s.trewartha_summer.mean_temp_c)} °C</Stat>}
        {n && <Stat label={<Term k="frostday">{t('zoneFrostDays')}</Term>}>{f(n.frost_days_yr, 0)}</Stat>}
        {n && <Stat label={<Term k="frostday">{t('zoneSpringFrost')}</Term>}>{f(n.spring_frost_days, 0)}</Stat>}
        {n && <Stat label={t('zoneHottest')}>{f(n.hottest_month_mean_c)} °C</Stat>}
      </div>
    </li>
  )
}

export function ZoneCard({ zone }: { zone: ZoneInfo }) {
  const t = useT()
  const lang = useLang()
  const nasa = zone.stations.find((s) => s.nasa_power)?.nasa_power
  return (
    <section className="card p-5 md:p-6 rise" style={{ borderLeft: `6px solid ${zone.color}` }}>
      <h2 className="font-display text-xl md:text-2xl font-extrabold mb-1 flex items-center gap-2.5">
        <span className="w-4 h-4 rounded-full shrink-0" style={{ background: zone.color }} />
        <span>{t('zoneCardTitle')}: {pick(zone.name, lang)}</span>
      </h2>
      <p className="text-sm text-muted mb-2">{pick(zone.desc, lang)}</p>
      <p className="text-base mb-4">
        {t('zoneElev', {
          f: fmt(zone.field_elevation_m, 0, lang), pos: t(POS[zone.elevation_position] ?? 'posMid'),
          a: fmt(zone.elevation_m.p10, 0, lang), b: fmt(zone.elevation_m.p90, 0, lang),
        })}
      </p>
      {zone.stations.length > 0 && (
        <>
          <h3 className="text-sm font-bold mb-2">{t('zoneStations')}</h3>
          <ul className="flex flex-col gap-3">
            {zone.stations.map((s) => <Station key={s.station} s={s} />)}
          </ul>
        </>
      )}
      <p className="text-xs text-muted mt-3">
        {zone.stations.filter((s) => s.url).map((s, i) => (
          <span key={s.station}>{i > 0 ? ' · ' : ''}
            <a className="underline" href={s.url} target="_blank" rel="noreferrer">{t('zoneSrcMgm')} ({s.name}) ↗</a>
          </span>
        ))}
        {nasa && <> · {t('zoneSrcNasa')}</>}
      </p>
      {lang === 'en' && <p className="text-xs text-muted mt-1">{t('zoneTypesNote')}</p>}
    </section>
  )
}
