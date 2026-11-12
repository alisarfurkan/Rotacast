import { useEffect, useRef } from 'react'
import type { EvidenceItem, Fact, SourceInfo, Strategy } from '../types'
import { SourceChip } from './Term'
import { CalendarStrip } from './Strategies'
import { useLang, useT } from '../ctx'
import { fmt, pick, unitLabel } from '../util'

function FactLine({ f, sources }: { f: Fact; sources: SourceInfo[] }) {
  const lang = useLang()
  const d = Math.abs(f.value) < 10 && f.value % 1 !== 0 ? 2 : Math.abs(f.value) < 100 && f.value % 1 !== 0 ? 1 : 0
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-surface2 px-2.5 py-1.5 text-xs">
      <span className="text-muted flex-1 min-w-[140px]">{pick(f.text, lang)}</span>
      <b className="tabular-nums text-sm text-ink">{fmt(f.value, d, lang)} <span className="font-medium text-muted">{unitLabel(f.unit, lang)}</span></b>
      <SourceChip id={f.source_id} sources={sources} />
    </div>
  )
}

function Items({ items, facts, sources }: { items: EvidenceItem[]; facts: Fact[]; sources: SourceInfo[] }) {
  const lang = useLang()
  const t = useT()
  return (
    <ul className="flex flex-col gap-3">
      {items.map((it, i) => {
        const fs = (it.facts ?? []).map((id) => facts.find((f) => f.id === id)).filter((f): f is Fact => !!f)
        return (
          <li key={i} className="text-[15px] leading-snug">
            <div className="flex gap-2"><span aria-hidden className="text-leaf mt-0.5">●</span><span>{pick(it.text, lang)}</span></div>
            {fs.length > 0 ? <div className="mt-1.5 ml-5 flex flex-col gap-1">{fs.map((f) => <FactLine key={f.id} f={f} sources={sources} />)}</div>
              : null}
            {fs.length === 0 && it.facts && it.facts.length > 0 && <div className="ml-5 text-xs text-muted">{t('noFacts')}</div>}
          </li>
        )
      })}
    </ul>
  )
}

function Block({ title, tone, children }: { title: string; tone: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="font-display text-lg font-extrabold mb-2 flex items-center gap-2"><i className="w-1.5 h-5 rounded" style={{ background: tone }} />{title}</h3>
      {children}
    </section>
  )
}

export function EvidenceDrawer({ s, facts, sources, onClose }: { s: Strategy | null; facts: Fact[]; sources: SourceInfo[]; onClose: () => void }) {
  const t = useT()
  const lang = useLang()
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!s) return
    const prev = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', k); document.body.style.overflow = ''; prev?.focus() }
  }, [s, onClose])
  if (!s) return null
  const ev = s.evidence
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={`${t('evTitle')}: ${pick(s.name, lang)}`}>
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="relative w-full max-w-xl h-full overflow-y-auto bg-bg shadow-2xl rise">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 px-5 py-4 border-b border-line" style={{ background: 'var(--surface)' }}>
          <div>
            <div className="text-[11px] uppercase tracking-widest text-muted">{t('evTitle')}</div>
            <h2 className="font-display text-2xl font-extrabold">{pick(s.name, lang)}</h2>
          </div>
          <button ref={closeRef} onClick={onClose} className="rounded-full border border-line px-3 py-1.5 text-sm font-semibold hover:bg-surface2">✕ {t('close')}</button>
        </div>
        <div className="p-5">
          <div className="mb-5"><CalendarStrip s={s} /></div>
          <Block title={t('evWhy')} tone="var(--water)"><Items items={ev.why} facts={facts} sources={sources} /></Block>
          <Block title={t('evBenefits')} tone="var(--leaf)"><Items items={ev.benefits} facts={facts} sources={sources} /></Block>
          <Block title={t('evGaps')} tone="var(--sun)">
            <ul className="flex flex-col gap-2">
              {ev.gaps.map((g, i) => <li key={i} className="flex gap-2 text-[15px]"><span aria-hidden>❔</span><span>{pick(g.text, lang)}</span></li>)}
            </ul>
          </Block>
          <Block title={t('evRisks')} tone="var(--bad)">
            <ul className="flex flex-col gap-2.5">
              {ev.risks.map((r, i) => (
                <li key={i} className="rounded-xl border border-line bg-badsoft/50 p-3 text-[15px]">
                  <div>⚠ {pick(r.text, lang)}</div>
                  {r.check_with && (
                    <span className="inline-block mt-1.5 rounded-full bg-bad text-bg text-[11px] font-bold px-2.5 py-0.5">
                      {r.check_with === 'agronomist' ? t('checkAgronomist') : r.check_with === 'extension_service' ? t('checkExtension') : r.check_with === 'market' ? t('checkMarket') : r.check_with === 'local_authority' ? t('checkLocal_authority') : r.check_with}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </Block>
          <p className="text-xs text-muted border-t border-line pt-3">{t('supportNote')}</p>
        </div>
      </aside>
    </div>
  )
}
