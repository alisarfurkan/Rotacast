import type { Band, CalendarEntry, CardsInfo, Strategy } from '../types'
import { CAT_COLOR, CROP_BY_ID } from '../crops'
import { Term } from './Term'
import { useLang, useT } from '../ctx'
import type { Key } from '../i18n'
import { fmt, mdToDoy, monthNames, pick, signed, to100 } from '../util'

const ICON: Record<string, string> = { baseline: '🌾', balanced_transition: '⚖️', low_risk: '🛡️', innovative: '🌿', water_saver: '💧', soil_builder: '🌱', balanced_income: '⚖️' }
const ACCENT: Record<string, string> = { baseline: '#7a6652', balanced_transition: '#c98a12', low_risk: '#1f6a93', innovative: '#4f8a35', water_saver: '#1f6a93', soil_builder: '#4f8a35', balanced_income: '#c98a12' }

/* ---------- planting calendar (rows = years of the cycle, columns = months) ---------- */
interface Seg { row: number; a: number; b: number; e: CalendarEntry; head: boolean }

function segments(cal: CalendarEntry[], cycle: number): Seg[] {
  const out: Seg[] = []
  for (const e of cal) {
    const s = mdToDoy(e.sow), h = mdToDoy(e.harvest)
    if (s <= h) out.push({ row: e.year, a: s, b: h, e, head: true })
    else {
      out.push({ row: e.year, a: 1, b: h, e, head: true })
      const prev = ((e.year - 2 + cycle) % cycle) + 1
      out.push({ row: prev, a: s, b: 365, e, head: false })
    }
  }
  return out
}

export function RotationChain({ s }: { s: Strategy }) {
  const t = useT()
  const lang = useLang()
  const mains = s.calendar.filter((e) => e.kind !== 'cover').sort((a, b) => a.year - b.year)
  return (
    <div className="flex flex-wrap items-center gap-1 text-[11px] mb-2" aria-label={t('calendar')}>
      {mains.map((m, i) => {
        const covers = s.calendar.filter((e) => e.kind === 'cover' && e.year === m.year)
        return (
          <span key={i} className="flex items-center gap-1 flex-wrap">
            {i > 0 && <span className="text-muted" aria-hidden>→</span>}
            <span className="rounded px-1.5 py-0.5 font-semibold text-white" style={{ background: CAT_COLOR[CROP_BY_ID[m.crop_id]?.cat ?? 'cereal'] }}>{pick(m.crop_name, lang)}</span>
            {covers.map((c, j) => (
              <span key={j} className="hatch rounded px-1.5 py-0.5 font-semibold text-white" style={{ background: CAT_COLOR.cover }}>
                +{pick(c.crop_name, lang)} {t('coverSuffix')}
              </span>
            ))}
          </span>
        )
      })}
      <span className="text-muted" aria-hidden>↻</span>
    </div>
  )
}

export function CalendarStrip({ s }: { s: Strategy }) {
  const t = useT()
  const lang = useLang()
  const segs = segments(s.calendar, s.cycle_years)
  const hasCover = s.calendar.some((e) => e.kind === 'cover')
  const rows = Array.from({ length: s.cycle_years }, (_, i) => i + 1)
  const mn = monthNames(lang)
  return (
    <div className="text-[10px]" role="img" aria-label={`${t('calendar')}: ` + s.calendar.map((e) => pick(e.crop_name, lang)).join(', ')}>
      <div className="grid grid-cols-[34px_1fr] gap-x-1">
        <span />
        <div className="grid grid-cols-12 text-muted text-[9px] mb-0.5">{mn.map((m, i) => <span key={i} className="text-center">{m[0]}</span>)}</div>
        {rows.map((r) => (
          <div key={r} className="contents">
            <span className="text-muted self-center font-semibold">{t('calYearN', { n: r })}</span>
            <div className="relative mb-1 rounded-sm overflow-hidden"
              style={{ height: hasCover ? 28 : 20, background: 'repeating-linear-gradient(135deg, var(--surface2) 0 4px, transparent 4px 8px)', border: '1px solid var(--line)' }}>
              {Array.from({ length: 11 }, (_, i) => <i key={i} className="absolute top-0 bottom-0 w-px bg-line opacity-60" style={{ left: ((i + 1) / 12) * 100 + '%' }} />)}
              {segs.filter((g) => g.row === r).map((g, i) => {
                const crop = CROP_BY_ID[g.e.crop_id]
                const color = CAT_COLOR[crop?.cat ?? 'cereal']
                const cover = g.e.kind === 'cover'
                const w = ((g.b - g.a + 1) / 365) * 100
                return (
                  <div key={i} title={`${pick(g.e.crop_name, lang)} (${g.e.sow} → ${g.e.harvest})`}
                    className={'absolute overflow-hidden whitespace-nowrap text-white font-semibold px-1 flex items-center ' + (cover ? 'hatch' : '')}
                    style={{ left: ((g.a - 1) / 365) * 100 + '%', width: w + '%', top: cover ? 20 : 1, height: cover ? 7 : 17,
                      background: color, borderRadius: 3, fontSize: 9.5,
                      borderBottom: g.e.irrigation === 'none' || cover ? undefined : `3px ${g.e.irrigation === 'full' ? 'solid' : 'dotted'} #8fd3ff`,
                      opacity: g.head ? 1 : 0.7 }}>
                    {!cover && w > 14 ? pick(g.e.crop_name, lang) : ''}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-muted mt-1">
        {Array.from(new Set(s.calendar.map((e) => e.crop_id))).map((id) => {
          const c = CROP_BY_ID[id]
          const nm = s.calendar.find((e) => e.crop_id === id)!.crop_name
          return (
            <span key={id} className="flex items-center gap-1">
              <i className={'inline-block w-2.5 h-2.5 rounded-sm ' + (c?.cat === 'cover' ? 'hatch' : '')} style={{ background: CAT_COLOR[c?.cat ?? 'cereal'] }} />
              {pick(nm, lang)}{c?.cat === 'cover' || s.calendar.find((e) => e.crop_id === id)?.kind === 'cover' ? ' ' + t('coverSuffix') : ''}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/* ---------- indicators ---------- */
function BandRow({ label, band, scale, unit, tip, higherBetter, decimals = 0 }: {
  label: React.ReactNode; band: Band; scale: [number, number]; unit: string; tip?: boolean; higherBetter: boolean | null; decimals?: number
}) {
  const lang = useLang()
  const [lo, hi] = scale
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo || 1)) * 100))
  const a = pos(band.p10), b = pos(band.p90), m = pos(band.p50)
  const color = higherBetter === null ? 'var(--water)' : higherBetter ? 'var(--leaf)' : 'var(--water)'
  return (
    <div>
      <div className="flex justify-between items-baseline text-xs">
        <span className="text-muted">{label}{tip ? null : null}</span>
        <span className="tabular-nums"><b className="text-sm text-ink">{fmt(band.p50, decimals, lang)}</b> <span className="text-muted">{unit}</span></span>
      </div>
      <div className="relative h-2.5 rounded-full bg-surface2 mt-1" role="img"
        aria-label={`${fmt(band.p10, decimals, lang)} – ${fmt(band.p90, decimals, lang)} ${unit}`}>
        <div className="absolute top-0 bottom-0 rounded-full opacity-40" style={{ left: a + '%', width: Math.max(1.5, b - a) + '%', background: color }} />
        <div className="absolute -top-0.5 -bottom-0.5 w-1 rounded bg-ink" style={{ left: `calc(${m}% - 2px)` }} />
      </div>
      <div className="flex justify-between text-[9.5px] text-muted tabular-nums mt-0.5">
        <span>{fmt(band.p10, decimals, lang)}</span><span>{fmt(band.p90, decimals, lang)}</span>
      </div>
    </div>
  )
}

function MeterRow({ label, value, max, unit, text, color, decimals = 0 }: { label: React.ReactNode; value: number; max: number; unit?: string; text?: string; color: string; decimals?: number }) {
  const lang = useLang()
  return (
    <div>
      <div className="flex justify-between items-baseline text-xs">
        <span className="text-muted">{label}</span>
        <span className="tabular-nums"><b className="text-sm text-ink">{text ?? fmt(value, decimals, lang)}</b> <span className="text-muted">{unit}</span></span>
      </div>
      <div className="h-2 rounded-full bg-surface2 mt-1 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: Math.max(2, Math.min(100, (Math.abs(value) / max) * 100)) + '%', background: color }} />
      </div>
    </div>
  )
}

function ScoreRing({ score, color }: { score: number; color: string }) {
  const r = 34, c = 2 * Math.PI * r
  return (
    <svg width="88" height="88" viewBox="0 0 88 88" role="img" aria-label={`${Math.round(score)} / 100`}>
      <circle cx="44" cy="44" r={r} fill="none" stroke="var(--surface2)" strokeWidth="9" />
      <circle cx="44" cy="44" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
        strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 44 44)" style={{ transition: 'stroke-dasharray .6s' }} />
      <text x="44" y="49" textAnchor="middle" className="font-display" style={{ fontSize: 24, fontWeight: 800, fill: 'var(--ink)' }}>{Math.round(score)}</text>
    </svg>
  )
}

const BD: { k: keyof Strategy['score_breakdown']; label: Key }[] = [
  { k: 'water', label: 'pWater' }, { k: 'soil', label: 'pSoil' }, { k: 'income', label: 'pIncome' },
  { k: 'erosion', label: 'pErosion' }, { k: 'risk', label: 'pRisk' },
]

function Delta({ text, good }: { text: string; good: boolean | null }) {
  const cls = good === null ? 'bg-surface2 text-muted' : good ? 'bg-leafsoft text-leaf' : 'bg-badsoft text-bad'
  return <span className={'inline-block rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ' + cls}>{text}</span>
}

export interface Scales { water: [number, number]; income: [number, number]; yield: [number, number] }
export function computeScales(list: Strategy[]): Scales {
  const rng = (f: (s: Strategy) => Band, pad = 0): [number, number] => {
    const all = list.flatMap((s) => [f(s).p10, f(s).p90])
    return [Math.min(0, Math.min(...all)) - pad, Math.max(...all)]
  }
  return { water: rng((s) => s.indicators.water_m3_ha_yr), income: rng((s) => s.indicators.income_usd_ha_yr), yield: [0, 1.05] }
}

function Parts({ s, accent }: { s: Strategy; accent: string }) {
  const t = useT()
  const lang = useLang()
  const parts = s.parts ?? []
  if (parts.length < 2) return null
  const pct = (x: number) => fmt(x * 100, 0, lang)
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden border border-line">
        {parts.map((p, k) => (
          <div key={k} style={{ width: p.share * 100 + '%', background: p.kind === 'rotation' ? accent : 'var(--leaf)',
            opacity: p.modeled || p.water_modeled ? 1 : 0.35 }} />
        ))}
      </div>
      <ul className="mt-1.5 grid gap-1 text-[11.5px]">
        {parts.map((p, k) => (
          <li key={k} className="min-w-0">
            <span className="font-bold tabular-nums">%{pct(p.share)}</span>{' '}
            {p.kind === 'rotation'
              ? <>{t(p.role === 'current_rotation' ? 'partCurrent' : 'partVerified')}{p.rotation_name && <span className="text-muted"> · {pick(p.rotation_name, lang)}</span>}</>
              : <>{t('partSpecialty')}: {p.crop ? <b>{pick(p.crop.name, lang)}</b> : <span className="italic text-muted">{t('partNotModeled')}</span>}
                {p.water && (
                  <div className="text-muted">
                    <div>{t('specWaterNeed', { etc: fmt(p.water.etc_mm.p50, 0, lang) })}</div>
                    <div>{t('specWaterRainfed', { eta: fmt(p.water.rainfed_eta_mm.p50, 0, lang) })}</div>
                    <div>{t('specWaterFull', { irr: fmt(p.water.irr_need_full_m3_ha.p50, 0, lang) })}</div>
                    <div className="text-[10.5px] italic">{t('specWaterNoIncome')}</div>
                  </div>
                )}
                {!p.crop && p.options && ([false, true] as const).map((per) => {
                  const list = p.options!.filter((o) => !!o.perennial === per)
                  return list.length > 0 && (
                    <div key={String(per)} className="text-muted">
                      {t(per ? 'partOptionsPerennial' : 'partOptionsAnnual', { list: list.map((o) => pick(o.name, lang)).join(', ') })}
                    </div>
                  )
                })}
                {(() => {
                  const ys = [p.crop, ...(p.options ?? [])].filter((c): c is NonNullable<typeof c> => !!c?.documented_yield)
                  return ys.length > 0 && (
                    <div className="text-muted">
                      {ys.map((c) => (
                        <div key={c.name.en} title={pick(c.documented_yield!.note, lang)}>
                          {pick(c.name, lang)}: {t('docYield', { y: fmt(c.documented_yield!.kg_da, 0, lang), yr: String(c.documented_yield!.year) })}
                        </div>
                      ))}
                      <div className="text-[10.5px] italic">{t('docYieldNoIncome')}</div>
                    </div>
                  )
                })()}</>}
          </li>
        ))}
      </ul>
      {s.coverage !== undefined && s.coverage < 0.999 && (
        <p className="mt-1.5 text-[11px] rounded-lg bg-surface2 px-2 py-1">ⓘ {t(s.water_coverage ? 'coverageNoteWater' : 'coverageNote', { p: pct(s.coverage) })}</p>
      )}
    </div>
  )
}

function Trials({ s }: { s: Strategy }) {
  const t = useT()
  const lang = useLang()
  if (!s.trials?.length) return null
  return (
    <div className="rounded-xl border border-dashed border-line p-3">
      <div className="text-xs font-bold">🧪 {t('trialsTitle')}</div>
      <p className="text-[11px] text-muted mb-1.5">{t('trialLabel')}</p>
      <ul className="grid gap-1.5 text-[11.5px]">
        {s.trials.map((tr, k) => (
          <li key={k}>
            <b>{pick(tr.crop.name, lang)}</b>
            <span className="text-muted"> · {t('trialShare', { a: fmt(tr.share_range[0] * 100, 0, lang), b: fmt(tr.share_range[1] * 100, 0, lang) })}
              {tr.crop.districts.length > 0 && <> · {tr.crop.districts.join(', ')}</>}</span>
            <div className="text-muted">{tr.modeled && tr.water_m3_ha_yr && tr.income_usd_ha_yr
              ? t('trialWater', { w: fmt(tr.water_m3_ha_yr.p50, 0, lang), i: fmt(tr.income_usd_ha_yr.p50, 0, lang) })
              : t('trialNoModel')}</div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function StrategyCard({ s, base, scales, top, onOpen }: { s: Strategy; base: Strategy; scales: Scales; top: boolean; onOpen: () => void }) {
  const t = useT()
  const lang = useLang()
  const accent = ACCENT[s.archetype] ?? '#7a6652'
  const isBase = s.id === base.id
  const i = s.indicators, bi = base.indicators
  const allScores = Object.values(s.score_breakdown)
  const dWater = i.water_m3_ha_yr.p50 - bi.water_m3_ha_yr.p50
  const dInc = i.income_usd_ha_yr.p50 - bi.income_usd_ha_yr.p50
  const dCover = i.soil_cover_days_yr - bi.soil_cover_days_yr
  const dN = i.n_balance_kg_ha_yr - bi.n_balance_kg_ha_yr
  const score = to100(s.score, [s.score])

  return (
    <article className={'card overflow-hidden flex flex-col ' + (top ? 'ring-2' : '')} style={top ? { boxShadow: `0 0 0 2px ${accent}` } : undefined}
      aria-label={pick(s.name, lang)}>
      <div className="px-4 pt-3 pb-3 text-white" style={{ background: accent }}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-[11px] uppercase tracking-widest opacity-85">{isBase ? t('stBaselineTag') : t('cycle', { n: s.cycle_years })}</div>
            <h3 className="font-display text-xl font-extrabold leading-tight mt-0.5">{ICON[s.archetype] ?? '🌾'} {pick(s.name, lang)}</h3>
          </div>
          {top && <span className="text-[10px] font-bold bg-white text-ink rounded-full px-2 py-0.5 shrink-0">★ {t(s.archetype === 'balanced_transition' ? 'stDefaultPick' : 'stTopPick')}</span>}
        </div>
      </div>

      <div className="p-4 flex flex-col gap-4 flex-1">
        <div className="flex items-center gap-3">
          <ScoreRing score={score} color={accent} />
          <div className="flex-1 grid gap-1">
            {BD.map(({ k, label }) => (
              <div key={k} className="flex items-center gap-1.5 text-[10.5px] text-muted">
                <span className="w-[74px] truncate">{t(label)}</span>
                <div className="flex-1 h-1.5 rounded bg-surface2 overflow-hidden"><div className="h-full rounded" style={{ width: to100(s.score_breakdown[k], allScores) + '%', background: accent }} /></div>
              </div>
            ))}
          </div>
        </div>

        <Parts s={s} accent={accent} />

        <div>
          <div className="text-xs font-bold mb-1">{t('calendar')}</div>
          <RotationChain s={s} />
          <CalendarStrip s={s} />
        </div>

        {/* headline water number */}
        <div className="rounded-xl p-3" style={{ background: 'var(--water-soft)' }}>
          <div className="text-[11px] font-bold uppercase tracking-wider text-water">💧 {t('water')}</div>
          <div className="flex items-baseline gap-1.5 flex-wrap">
            <span className="font-display text-4xl font-black text-water tabular-nums leading-none">{fmt(i.water_m3_ha_yr.p50, 0, lang)}</span>
            <span className="text-xs text-muted">{t('waterUnit')}</span>
          </div>
          {!isBase && <div className="mt-1.5"><Delta good={dWater < 0 ? true : dWater > 0 ? false : null} text={`${signed(dWater, 0, lang)} ${t('waterUnit')}`} /> <span className="text-[10.5px] text-muted">{t('vsCurrent')}</span></div>}
          <div className="mt-2"><BandRow label={<Term k="band">{t('water')}</Term>} band={i.water_m3_ha_yr} scale={[0, Math.max(scales.water[1], 1)]} unit="" higherBetter={null} /></div>
        </div>

        <div className="grid gap-3.5">
          <BandRow label={<Term k="income">{t('income')}</Term>} band={i.income_usd_ha_yr} scale={scales.income} unit={t('incomeUnit')} higherBetter />
          {!isBase && <div className="-mt-2"><Delta good={dInc > 0 ? true : dInc < 0 ? false : null} text={`${signed(dInc, 0, lang)} USD/ha`} /></div>}
          <BandRow label={<Term k="yield">{t('yieldRatio')}</Term>} band={i.yield_ratio} scale={scales.yield} unit="" higherBetter decimals={2} />
          <MeterRow label={<Term k="nbalance">{t('nBalance')}</Term>} value={i.n_balance_kg_ha_yr} max={60} unit={t('nUnit')}
            text={signed(i.n_balance_kg_ha_yr, 0, lang)} color={i.n_balance_kg_ha_yr >= 0 ? 'var(--leaf)' : 'var(--bad)'} />
          <MeterRow label={t('coverDays')} value={i.soil_cover_days_yr} max={365} unit={t('daysUnit')} color="var(--leaf)" />
          {!isBase && <div className="-mt-2 flex gap-1 flex-wrap">
            <Delta good={dCover > 0 ? true : dCover < 0 ? false : null} text={`${signed(dCover, 0, lang)} ${t('daysUnit')}`} />
            <Delta good={dN > 0 ? true : dN < 0 ? false : null} text={`${signed(dN, 0, lang)} kg N`} />
          </div>}
          <MeterRow label={<Term k="erosion">{t('erosion')}</Term>} value={i.erosion_rel} max={1.2} decimals={2} color={i.erosion_rel <= 1 ? 'var(--leaf)' : 'var(--bad)'} />
          <div className="grid grid-cols-2 gap-2">
            <MeterRow label={<Term k="frost">{'❄ ' + (lang === 'tr' ? 'Don' : 'Frost')}</Term>} value={i.frost_risk * 100} max={50} text={fmt(i.frost_risk * 100, 0, lang) + '%'} color="var(--water)" />
            <MeterRow label={<Term k="heat">{'☀ ' + (lang === 'tr' ? 'Sıcak' : 'Heat')}</Term>} value={i.heat_risk * 100} max={50} text={fmt(i.heat_risk * 100, 0, lang) + '%'} color="var(--sun)" />
          </div>
        </div>

        <Trials s={s} />

        <button onClick={onOpen} className="btn-primary mt-auto py-2.5 text-sm" aria-haspopup="dialog">
          📋 {t('openEvidence')}
        </button>
      </div>
    </article>
  )
}

const NOTE_KEY: Record<string, Key> = {
  no_candidate_within_limits: 'noteNoCandidate', no_verified_specialty: 'noteNoSpecialty', no_local_evidence: 'noteNoLocal',
}

export function Strategies({ strategies, onOpen, cards }: { strategies: Strategy[]; onOpen: (id: string) => void; cards?: CardsInfo | null }) {
  const t = useT()
  const lang = useLang()
  const base = strategies.find((s) => s.archetype === 'baseline') ?? strategies[0]
  const ordered = [base, ...strategies.filter((s) => s !== base)]
  const scales = computeScales(ordered)
  const alts = ordered.filter((s) => s !== base)
  const top = alts.find((s) => s.archetype === 'balanced_transition')
    ?? (alts.length ? alts.reduce((a, b) => (b.score > a.score ? b : a)) : null)
  const saver = alts.length ? alts.reduce((a, b) => (b.indicators.water_m3_ha_yr.p50 < a.indicators.water_m3_ha_yr.p50 ? b : a)) : null
  const saved = saver ? base.indicators.water_m3_ha_yr.p50 - saver.indicators.water_m3_ha_yr.p50 : 0
  return (
    <section aria-labelledby="st-title" className="rise">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h2 id="st-title" className="font-display text-2xl md:text-3xl font-extrabold text-soil">{t('stTitle')}</h2>
        <span className="text-xs text-muted">{t('stSub')}</span>
      </div>
      <p className="font-display text-lg md:text-xl leading-snug mb-4 rounded-xl bg-watersoft px-4 py-3 border-l-4 border-water">
        {saver && saved > 0 ? t('headlineSave', { name: pick(saver.name, lang), amount: fmt(saved, 0, lang) }) : t('headlineNone')}
      </p>
      <p className="text-xs text-muted mb-1">{t('rangeHint')}</p>
      {cards && <p className="text-xs text-muted mb-3">{t('limitsNote', { w: fmt(cards.limits.water_m3_ha_yr_max, 0, lang) })}
        {ordered.some((s) => s.coverage !== undefined && s.coverage < 0.999 && !s.water_coverage) && <> {t('limitsPartial')}</>}</p>}
      {cards && Object.values(cards.notes).map((n) => NOTE_KEY[n] && (
        <p key={n} className="text-sm rounded-lg border border-line bg-surface2 px-3 py-2 mb-3">ⓘ {t(NOTE_KEY[n])}</p>
      ))}
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        {ordered.map((s) => (
          <StrategyCard key={s.id} s={s} base={base} scales={scales} top={s === top} onOpen={() => onOpen(s.id)} />
        ))}
      </div>
    </section>
  )
}
