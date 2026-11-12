import { GLOSSARY } from '../i18n'
import { useLang } from '../ctx'

/** Inline jargon word with a plain-language tooltip (hover, focus or tap). */
export function Term({ k, children }: { k: keyof typeof GLOSSARY | string; children?: React.ReactNode }) {
  const lang = useLang()
  const g = GLOSSARY[k]?.[lang]
  if (!g) return <>{children}</>
  return (
    <span className="term" tabIndex={0} role="note">
      {children ?? g.term}
      <span className="tip" role="tooltip">
        <strong className="block mb-0.5">{g.term}</strong>
        {g.def}
      </span>
    </span>
  )
}

export function SourceChip({ id, sources }: { id: string; sources: { id: string; name: string; url: string }[] }) {
  const s = sources.find((x) => x.id === id)
  const name = s?.name ?? id
  const cls = 'inline-flex items-center gap-1 rounded-full bg-watersoft text-water text-[11px] font-semibold px-2 py-0.5 whitespace-nowrap'
  return s?.url ? (
    <a className={cls} href={s.url} target="_blank" rel="noreferrer">{name} ↗</a>
  ) : (
    <span className={cls}>{name}</span>
  )
}
