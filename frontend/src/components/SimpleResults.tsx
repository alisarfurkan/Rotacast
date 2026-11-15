import type { Strategy, FieldReport } from '../types'
import { useLang, useT } from '../ctx'
import type { Key } from '../i18n'
import { pick } from '../util'
import { aboutFacts, cropChain, simpleDeltas, type Trend } from '../simple'

const ICON: Record<string, string> = { baseline: '🌾', balanced_transition: '⚖️', low_risk: '🛡️', innovative: '🌿', water_saver: '💧', soil_builder: '🌱', balanced_income: '⚖️' }
const ACCENT: Record<string, string> = { baseline: '#7a6652', balanced_transition: '#c98a12', low_risk: '#1f6a93', innovative: '#4f8a35', water_saver: '#1f6a93', soil_builder: '#4f8a35', balanced_income: '#c98a12' }
const CHECK: Record<string, Key> = {
  agronomist: 'checkAgronomist', extension_service: 'checkExtension', market: 'checkMarket', local_authority: 'checkLocal_authority',
}

const ARROW: Record<Trend, string> = { up: '↑', down: '↓', same: '=' }

function Row({ icon, label, trend, word, goodWhen }: { icon: string; label: string; trend: Trend; word: string; goodWhen: 'up' | 'down' }) {
  const tone = trend === 'same' ? 'text-muted bg-surface2' : trend === goodWhen ? 'text-leaf bg-leafsoft' : 'text-bad bg-badsoft'
  return (
    <li className="flex items-center gap-2 text-[15px]">
      <span aria-hidden className="text-xl w-7 text-center shrink-0">{icon}</span>
      <span className="font-semibold min-w-0 flex-1">{label}</span>
      <span className={'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-bold ' + tone}>
        <span aria-hidden className="text-lg leading-none">{ARROW[trend]}</span>{word}
      </span>
    </li>
  )
}

function SimpleCard({ s, base }: { s: Strategy; base: Strategy }) {
  const t = useT()
  const lang = useLang()
  const accent = ACCENT[s.archetype] ?? '#7a6652'
  const isBase = s === base
  const d = isBase ? null : simpleDeltas(s, base)
  const why = s.evidence.why.slice(0, 2)
  const risk = s.evidence.risks[0]
  const chk = risk?.check_with
  return (
    <article className="card overflow-hidden flex flex-col min-w-0" aria-label={pick(s.name, lang)}>
      <div className="px-4 py-3 text-white" style={{ background: accent }}>
        <div className="text-[11px] uppercase tracking-widest opacity-85">{isBase ? t('stBaselineTag') : t('cycle', { n: s.cycle_years })}</div>
        <h3 className="font-display text-xl font-extrabold leading-tight mt-0.5 break-words">{ICON[s.archetype] ?? '🌾'} {pick(s.name, lang)}</h3>
      </div>
      <div className="p-4 flex flex-col gap-4 flex-1 min-w-0">
        <p className="text-[15px] font-semibold leading-snug break-words">{cropChain(s, lang)}</p>
        {d ? (
          <div>
            <div className="text-xs text-muted mb-1.5">{t('vsCurrent')}</div>
            <ul className="flex flex-col gap-2">
              <Row icon="💧" label={t('sWater')} trend={d.water} goodWhen="down"
                word={t(d.water === 'down' ? 'sWaterDown' : d.water === 'up' ? 'sWaterUp' : 'sSame')} />
              <Row icon="💰" label={t('income')} trend={d.income} goodWhen="up"
                word={t(d.income === 'up' ? 'sIncomeUp' : d.income === 'down' ? 'sIncomeDown' : 'sSame')} />
              <Row icon="🌱" label={t('sSoil')} trend={d.soil} goodWhen="up"
                word={t(d.soil === 'up' ? 'sSoilUp' : d.soil === 'down' ? 'sSoilDown' : 'sSame')} />
            </ul>
          </div>
        ) : <p className="text-sm text-muted">{t('sBaseNote')}</p>}
        {!isBase && why.length > 0 && (
          <div>
            <h4 className="text-sm font-bold mb-1">{t('sWhy')}</h4>
            <ul className="flex flex-col gap-1">
              {why.map((w, i) => <li key={i} className="text-sm leading-snug break-words">{pick(w.text, lang)}</li>)}
            </ul>
          </div>
        )}
        {!isBase && risk && (
          <div>
            <h4 className="text-sm font-bold mb-1">{t('sWho')}</h4>
            <p className="text-sm leading-snug break-words">
              {chk && <span className="inline-block mr-1.5 rounded-full bg-bad text-bg text-[11px] font-bold px-2.5 py-0.5 align-middle">{CHECK[chk] ? t(CHECK[chk]) : chk}</span>}
              {pick(risk.text, lang)}
            </p>
          </div>
        )}
      </div>
    </article>
  )
}

export function SimpleResults({ strategies, onDetails }: { strategies: Strategy[]; onDetails: (id: string) => void }) {
  const t = useT()
  const base = strategies.find((s) => s.archetype === 'baseline') ?? strategies[0]
  const ordered = [base, ...strategies.filter((s) => s !== base)]
  return (
    <section aria-labelledby="sr-title" className="rise">
      <h2 id="sr-title" className="font-display text-2xl md:text-3xl font-extrabold text-soil mb-1">{t('sTitle')}</h2>
      <p className="text-sm text-muted mb-4">{t('sSub')}</p>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {ordered.map((s) => (
          <div key={s.id} className="flex flex-col gap-2 min-w-0">
            <SimpleCard s={s} base={base} />
            {s !== base && (
              <button onClick={() => onDetails(s.id)} className="self-start text-sm font-semibold text-water underline underline-offset-2 hover:no-underline px-1">
                {t('sDetails')} →
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

export function AboutField({ report }: { report: FieldReport }) {
  const t = useT()
  const lang = useLang()
  const lines = aboutFacts(report.facts, lang)
  if (!lines.length) return null
  return (
    <section className="card p-5 rise" aria-labelledby="af-title">
      <h2 id="af-title" className="font-display text-xl md:text-2xl font-extrabold text-soil mb-2">{t('sAbout')}</h2>
      <ul className="flex flex-col gap-2">
        {lines.map((l, i) => <li key={i} className="flex gap-2 text-[15px] leading-snug"><span aria-hidden className="text-leaf">●</span><span className="min-w-0 break-words">{l}</span></li>)}
      </ul>
    </section>
  )
}
