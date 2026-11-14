import type { FieldReport } from '../types'
import { CROP_BY_ID } from '../crops'
import { useLang, useT } from '../ctx'
import { fmt, pick, signed } from '../util'

/** "Your inputs" (Advanced): what the farmer entered next to the satellite/model estimate, plus the declared-vs-modelled checks. */
export function UserInputs({ report }: { report: FieldReport }) {
  const t = useT()
  const lang = useLang()
  const ui = report.user_inputs ?? []
  const q = report.quota
  const yc = report.yield_check ?? []
  const hc = report.history_check
  const ic = report.irrigation_check ?? []
  const cn = (id: string) => pick(CROP_BY_ID[id]?.name, lang) || id
  if (!ui.length && !yc.length && !hc && !ic.length && !(q?.baseline_exceeds)) return null

  return (
    <section className="card p-5 md:p-6 rise min-w-0" aria-labelledby="ui-title">
      <h2 id="ui-title" className="font-display text-xl md:text-2xl font-extrabold text-soil mb-3">{t('uiTitle')}</h2>
      {q?.baseline_exceeds && (
        <p role="alert" className="mb-3 rounded-lg bg-badsoft text-bad text-sm font-semibold px-3 py-2">⚠ {t('uiBaseOver')}</p>
      )}
      {ui.length > 0 && (
        <ul className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
          {ui.map((u) => (
            <li key={u.id} className="rounded-xl border border-line bg-surface2 p-3 min-w-0">
              <div className="text-xs font-bold uppercase tracking-wide text-muted">{pick(u.label, lang)}</div>
              <div className="mt-1 text-[15px] font-semibold break-words">{pick(u.value, lang)}</div>
              {u.model && (
                <div className="mt-1 text-xs text-muted break-words">{t('uiModel')}: {pick(u.model, lang)}</div>
              )}
            </li>
          ))}
        </ul>
      )}
      {(yc.length > 0 || hc || ic.length > 0) && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {yc.length > 0 && (
            <div className="min-w-0">
              <h3 className="text-sm font-bold mb-1.5">{t('ycTitle')}</h3>
              <ul className="flex flex-col gap-1 text-sm">
                {yc.map((y) => (
                  <li key={y.crop_id} className="break-words">
                    <b>{cn(y.crop_id)}</b>: {t('ycLine', { declared: fmt(y.declared_t_ha, 1, lang), regional: fmt(y.regional_t_ha, 1, lang), pct: fmt(Math.abs(y.factor - 1) * 100, 0, lang), dir: t(y.factor >= 1 ? 'ycAbove' : 'ycBelow') })}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {hc && (
            <div className="min-w-0">
              <h3 className="text-sm font-bold mb-1.5">{t('hcTitle')}</h3>
              <p className="text-sm">{hc.n_years ? t('hcLine', { agree: hc.n_agree, n: hc.n_years }) : t('hcNone')}</p>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {hc.years.map((y) => (
                  <li key={y.year} title={cn(y.crop_id)}
                    className={'rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ' + (y.agree === null ? 'bg-surface2 text-muted' : y.agree ? 'bg-leafsoft text-leaf' : 'bg-badsoft text-bad')}>
                    {y.year} {y.agree === null ? '?' : y.agree ? '✓' : '✗'}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {ic.length > 0 && (
            <div className="min-w-0">
              <h3 className="text-sm font-bold mb-1.5">{t('icTitle')}</h3>
              <ul className="flex flex-col gap-1 text-sm">
                {ic.map((r) => (
                  <li key={r.crop_id} className="break-words">
                    <b>{cn(r.crop_id)}</b>: {r.modelled_m3_ha === null
                      ? t('icNoModel', { declared: fmt(r.declared_m3_ha, 0, lang) })
                      : t('icLine', { declared: fmt(r.declared_m3_ha, 0, lang), modelled: fmt(r.modelled_m3_ha, 0, lang), diff: r.diff_pct === null ? '' : signed(r.diff_pct, 1, lang) + ' %' })}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
