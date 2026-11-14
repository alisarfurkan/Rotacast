import type { ZoneCrops, ZoneInfo, ZoneStation } from '../types'
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

const GROUP_ORDER = ['field', 'special', 'protected', 'method', 'tech'] as const

function Crops({ c }: { c: ZoneCrops }) {
  const t = useT()
  const lang = useLang()
  const num = (id: string) => c.sources.findIndex((s) => s.id === id) + 1
  return (
    <div className="mt-5">
      <h3 className="text-sm font-bold mb-1">{t('zoneCropsTitle')}</h3>
      <p className="text-xs text-muted mb-3">{t('zoneCropsNote')} {pick(c.caveat, lang)}</p>
      {c.notes.map((n, i) => (
        <p key={i} className="text-sm rounded-lg border border-line bg-surface2 px-3 py-2 mb-3">
          ⚠ {pick(n, lang)}{n.sources.map((s) => <sup key={s} className="text-muted ml-0.5">[{num(s)}]</sup>)}
        </p>
      ))}
      {GROUP_ORDER.map((g) => {
        const items = c.crops.filter((x) => x.group === g)
        if (!items.length) return null
        return (
          <div key={g} className="mb-3">
            <div className="text-[11px] uppercase tracking-wide text-muted mb-1.5">{pick(c.groups[g], lang)}</div>
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-2">
              {items.map((x) => (
                <li key={x.name.en} className={`rounded-lg border px-3 py-2 text-sm min-w-0 ${x.status === 'pilot' ? 'border-dashed border-line' : 'border-line bg-surface2'}`}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-semibold">{pick(x.name, lang)}</span>
                    {x.status === 'pilot' && (
                      <span title={t('zoneCropPilotTip')} className="text-[11px] rounded-full border border-line px-1.5">🧪 {t('zoneCropPilot')}</span>
                    )}
                    {x.caution && (
                      <span title={t('zoneCropCautionTip')} className="text-[11px] rounded-full border border-line px-1.5">⚠ {t('zoneCropCaution')}</span>
                    )}
                    {x.sources.map((s) => <sup key={s} className="text-muted">[{num(s)}]</sup>)}
                  </div>
                  {(x.districts?.length || x.note) && (
                    <div className="text-xs text-muted mt-0.5">
                      {x.districts?.join(', ')}{x.districts?.length && x.note ? ' · ' : ''}{x.note && pick(x.note, lang)}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
      <details className="text-xs text-muted mt-2">
        <summary className="cursor-pointer">{t('zoneCropSources')} ({c.sources.length})</summary>
        <ol className="list-decimal pl-5 mt-1.5 flex flex-col gap-1">
          {c.sources.map((s) => (
            <li key={s.id}>
              {s.url ? <a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.title} ↗</a>
                : <>{s.title} <span className="italic">({t('zoneCropNoUrl')})</span></>}
            </li>
          ))}
        </ol>
      </details>
    </div>
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
      {zone.crops && zone.crops.crops.length > 0 && <Crops c={zone.crops} />}
    </section>
  )
}
