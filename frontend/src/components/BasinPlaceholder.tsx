import { useT } from '../ctx'

export function BasinPlaceholder() {
  const t = useT()
  return (
    <section className="card p-8 md:p-14 text-center max-w-3xl mx-auto mt-6">
      <svg viewBox="0 0 400 120" className="mx-auto w-full max-w-md mb-6" aria-hidden>
        <path d="M0 90 C60 30 110 110 170 70 S280 20 400 80 V120 H0Z" fill="var(--water-soft)" />
        <path d="M0 105 C80 70 140 120 210 95 S330 60 400 100 V120 H0Z" fill="var(--leaf-soft)" />
        {[60, 120, 200, 270, 330].map((x, i) => <rect key={x} x={x} y={60 + (i % 2) * 14} width="26" height="16" rx="3" fill="var(--sun)" opacity=".75" />)}
      </svg>
      <span className="inline-block rounded-full bg-sunsoft text-sun text-xs font-bold px-3 py-1 mb-3">{t('basinSoon')}</span>
      <h2 className="font-display text-3xl font-extrabold mb-3">{t('basinTitle')}</h2>
      <p className="text-muted max-w-xl mx-auto">{t('basinText')}</p>
    </section>
  )
}
