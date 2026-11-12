import type { Lang } from '../types'
import { useT } from '../ctx'

export type Tab = 'field' | 'basin'

export function Header({ lang, setLang, tab, setTab }: { lang: Lang; setLang: (l: Lang) => void; tab: Tab; setTab: (t: Tab) => void }) {
  const t = useT()
  const chips = ['NASA POWER', 'MODIS NDVI', 'NASADEM', 'SoilGrids']
  return (
    <header className="bg-soil text-bg" style={{ background: 'linear-gradient(135deg, #3b2616 0%, #5a3b22 55%, #3d5a2c 130%)', color: '#f6efe0' }}>
      <div className="mx-auto max-w-[1500px] px-4 md:px-8 pt-4 pb-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <svg width="40" height="40" viewBox="0 0 32 32" aria-hidden>
              <rect width="32" height="32" rx="9" fill="#f6efe0" />
              <path d="M16 5c4.2 3 6.4 7 6.4 11.2a6.4 6.4 0 0 1-12.8 0C9.6 12 11.800 8 16 5z" fill="#4f9a3a" />
              <path d="M16 11v15" stroke="#3b2616" strokeWidth="1.6" />
              <path d="M3 27c5-2 9-2 13 0s8 2 13 0" stroke="#1f6a93" strokeWidth="2" fill="none" />
            </svg>
            <div>
              <h1 className="font-display text-3xl md:text-4xl font-extrabold leading-none tracking-tight">{t('appName')}</h1>
              <p className="text-[13px] md:text-sm opacity-85 mt-1 max-w-xl">{t('tagline')}</p>
            </div>
          </div>
          <div role="group" aria-label="Language" className="flex rounded-full border border-white/30 overflow-hidden text-sm font-semibold shrink-0">
            {(['tr', 'en'] as Lang[]).map((l) => (
              <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
                className={'px-3 py-1.5 transition ' + (lang === l ? 'bg-[#f6efe0] text-[#3b2616]' : 'hover:bg-white/10')}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-widest opacity-70 mr-1">{t('nasaInside')}</span>
          {chips.map((c) => (
            <span key={c} className="text-[11px] font-semibold rounded-full border border-white/30 bg-white/10 px-2.5 py-1">{c}</span>
          ))}
        </div>
        <nav className="mt-4 flex gap-1" aria-label="Views">
          {(['field', 'basin'] as Tab[]).map((x) => (
            <button key={x} onClick={() => setTab(x)} aria-current={tab === x ? 'page' : undefined}
              className={'px-4 py-2 rounded-t-xl text-sm font-semibold transition ' + (tab === x ? 'bg-[var(--bg)] text-[var(--ink)]' : 'hover:bg-white/10')}>
              {x === 'field' ? t('tabField') : t('tabBasin')}
            </button>
          ))}
        </nav>
      </div>
    </header>
  )
}
