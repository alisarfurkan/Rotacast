import { useEffect, useState } from 'react'
import { useT } from '../ctx'
import type { Key } from '../i18n'

const STEPS: { key: Key; at: number }[] = [
  { key: 'load1', at: 0 },
  { key: 'load2', at: 2500 },
  { key: 'load3', at: 6000 },
  { key: 'load4', at: 8000 },
  { key: 'load5', at: 10500 },
  { key: 'load6', at: 14000 },
]

export function Loading() {
  const t = useT()
  const [ms, setMs] = useState(0)
  useEffect(() => {
    const start = Date.now()
    const id = setInterval(() => setMs(Date.now() - start), 300)
    return () => clearInterval(id)
  }, [])
  const active = STEPS.filter((s) => ms >= s.at).length - 1
  const pct = Math.min(94, 6 + (1 - Math.exp(-ms / 9000)) * 90)
  return (
    <section className="card p-6 md:p-10 max-w-2xl mx-auto mt-6 rise" aria-live="polite" role="status">
      <h2 className="font-display text-2xl font-extrabold mb-1">{t('loadTitle')}</h2>
      <p className="text-sm text-muted mb-5">{t('loadWait')}</p>
      <div className="h-3 rounded-full bg-surface2 overflow-hidden mb-6">
        <div className="h-full rounded-full bar-anim transition-all duration-500" style={{ width: pct + '%', backgroundColor: 'var(--leaf)' }} />
      </div>
      <ul className="flex flex-col gap-2.5">
        {STEPS.map((s, i) => (
          <li key={s.key} className={'flex items-center gap-3 text-sm transition-opacity ' + (i > active ? 'opacity-35' : '')}>
            <span className={'w-5 h-5 rounded-full grid place-items-center text-[11px] font-bold ' +
              (i < active ? 'bg-leaf text-bg' : i === active ? 'bg-water text-bg animate-pulse' : 'bg-surface2')}>
              {i < active ? '✓' : ''}
            </span>
            <span className={i === active ? 'font-semibold' : ''}>{t(s.key)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
