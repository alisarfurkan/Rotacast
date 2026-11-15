import { useEffect, useState } from 'react'
import { CROPS, CROP_BY_ID } from '../crops'
import { useLang, useT } from '../ctx'
import { pick } from '../util'
import { METHODS, REASONS, TEXTURES, errFor, rotationCrops, type DetailsForm } from '../fieldDetails'
import type { RotationStep } from '../types'

const input = 'w-full min-w-0 rounded-lg border border-line bg-surface px-3 py-2 text-base'
const hintCls = 'text-xs text-muted'

function Err({ msg }: { msg?: string }) {
  return msg ? <p role="alert" className="text-xs font-semibold text-bad mt-1 break-words">{msg}</p> : null
}

function Group({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  const t = useT()
  return (
    <fieldset className="rounded-xl border border-line bg-surface2 p-3.5 min-w-0">
      <legend className="px-1 text-base font-semibold">{title}</legend>
      <p className={hintCls + ' mb-2.5'}>{hint ?? t('detBlank')}</p>
      {children}
    </fieldset>
  )
}

function Num({ label, value, onChange, error, unit }: { label: string; value: string; onChange: (v: string) => void; error?: string; unit?: string }) {
  return (
    <label className="block min-w-0">
      <span className="block text-sm font-medium mb-1">{label}</span>
      <div className="flex items-center gap-1.5">
        <input type="text" inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error} className={input + (error ? ' border-bad' : '')} />
        {unit && <span className="text-sm text-muted shrink-0">{unit}</span>}
      </div>
      <Err msg={error} />
    </label>
  )
}

interface Props {
  form: DetailsForm
  setForm: (f: DetailsForm) => void
  rotation: RotationStep[]
  hasArea: boolean
  errors: Record<string, string>
}

export function DetailsPanel({ form, setForm, rotation, hasArea, errors }: Props) {
  const t = useT()
  const lang = useLang()
  const [open, setOpen] = useState(false)
  const hasErr = Object.keys(errors).length > 0
  useEffect(() => { if (hasErr) setOpen(true) }, [hasErr])
  const patch = (p: Partial<DetailsForm>) => setForm({ ...form, ...p })
  const crops = rotationCrops(rotation)
  const cropName = (id: string) => pick(CROP_BY_ID[id]?.name, lang) || id
  const lastYear = new Date().getFullYear() - 1

  const usedExcl = new Set(form.excluded.map((e) => e.crop_id))
  const addExcl = () => {
    const c = CROPS.find((x) => !usedExcl.has(x.id))
    if (c) patch({ excluded: [...form.excluded, { crop_id: c.id, reason: 'not_wanted' }] })
  }
  const setExcl = (i: number, p: Partial<DetailsForm['excluded'][number]>) =>
    patch({ excluded: form.excluded.map((e, j) => (j === i ? { ...e, ...p } : e)) })

  const usedYears = new Set(form.history.map((h) => h.year))
  const addHist = () => {
    let y = lastYear
    while (usedYears.has(String(y)) && y > 2000) y--
    patch({ history: [...form.history, { year: String(y), crop_id: crops[0] ?? 'wheat_winter' }] })
  }
  const setHist = (i: number, p: Partial<DetailsForm['history'][number]>) =>
    patch({ history: form.history.map((h, j) => (j === i ? { ...h, ...p } : h)) })

  return (
    <section className="card p-5 md:p-6 lg:col-span-2 min-w-0">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="details-body"
        className="w-full flex items-center justify-between gap-3 text-left">
        <span className="font-display text-xl md:text-2xl font-extrabold text-soil min-w-0 break-words">{t('detTitle')}</span>
        <span aria-hidden className="text-2xl text-muted shrink-0">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div id="details-body" className="mt-4 flex flex-col gap-4">
          <p className="text-sm text-muted">{t('detIntro')}</p>

          <Group title={t('detSoil')}>
            <label className="block mb-3">
              <span className="block text-sm font-medium mb-1">{t('detTexture')}</span>
              <select value={form.texture} onChange={(e) => patch({ texture: e.target.value })} className={input}>
                <option value="">{t('detUnknown')}</option>
                {TEXTURES.map((x) => <option key={x.id} value={x.id}>{x[lang]}</option>)}
              </select>
              <Err msg={errFor(errors, 'soil.texture_class')} />
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Num label={t('detClay')} value={form.clay} onChange={(v) => patch({ clay: v })} error={errFor(errors, 'soil.clay_pct')} unit="%" />
              <Num label={t('detSand')} value={form.sand} onChange={(v) => patch({ sand: v })} error={errFor(errors, 'soil.sand_pct')} unit="%" />
              <Num label={t('detSoc')} value={form.soc} onChange={(v) => patch({ soc: v })} error={errFor(errors, 'soil.soc_gkg')} unit="g/kg" />
              <Num label="pH" value={form.ph} onChange={(v) => patch({ ph: v })} error={errFor(errors, 'soil.ph')} />
            </div>
            <Err msg={errors['soil']} />
          </Group>

          <Group title={t('detExcl')}>
            <ul className="flex flex-col gap-2">
              {form.excluded.map((e, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <select aria-label={t('detCrop')} value={e.crop_id} onChange={(ev) => setExcl(i, { crop_id: ev.target.value })} className={input + ' flex-1 basis-40'}>
                    {CROPS.filter((c) => c.id === e.crop_id || !usedExcl.has(c.id)).map((c) => <option key={c.id} value={c.id}>{pick(c.name, lang)}</option>)}
                  </select>
                  <select aria-label={t('detReason')} value={e.reason} onChange={(ev) => setExcl(i, { reason: ev.target.value as typeof e.reason })} className={input + ' flex-1 basis-40'}>
                    {REASONS.map((r) => <option key={r.id} value={r.id}>{t(r.key)}</option>)}
                  </select>
                  <button onClick={() => patch({ excluded: form.excluded.filter((_, j) => j !== i) })} aria-label={t('remove')}
                    className="px-2 py-1 text-lg text-bad hover:bg-badsoft rounded">✕</button>
                </li>
              ))}
            </ul>
            <button onClick={addExcl} disabled={usedExcl.size >= CROPS.length}
              className="mt-2 rounded-lg border-2 border-dashed border-line px-3 py-2 text-sm font-semibold text-muted hover:border-leaf hover:text-leaf">
              + {t('detExclAdd')}
            </button>
            <Err msg={errFor(errors, 'excluded_crops')} />
          </Group>

          <Group title={t('detMethod')}>
            <div className="flex flex-wrap gap-2" role="group" aria-label={t('detMethod')}>
              {METHODS.map((m) => (
                <button key={m.id} onClick={() => patch({ method: form.method === m.id ? '' : m.id })} aria-pressed={form.method === m.id}
                  className={'flex-1 basis-24 rounded-lg py-2.5 text-sm font-semibold border ' + (form.method === m.id ? 'bg-water text-bg border-water' : 'border-line bg-surface hover:bg-leafsoft')}>
                  {t(m.key)}
                </button>
              ))}
            </div>
            <Err msg={errFor(errors, 'irrigation_method')} />
          </Group>

          <Group title={t('detQuota')}>
            <div className="max-w-sm">
              <Num label={hasArea ? t('detQuotaField') : t('detQuotaHa')} value={form.quota} onChange={(v) => patch({ quota: v })}
                error={errFor(errors, 'water_quota_m3_yr')} />
            </div>
            <p className={hintCls + ' mt-1.5'}>{t('detQuotaHint')}</p>
          </Group>

          <Group title={t('detYields')} hint={t('detYieldsHint')}>
            <div className="grid sm:grid-cols-2 gap-3">
              {crops.map((c) => (
                <Num key={c} label={cropName(c)} unit="t/ha" value={form.yields[c] ?? ''}
                  onChange={(v) => patch({ yields: { ...form.yields, [c]: v } })} error={errFor(errors, 'yields_t_ha.' + c)} />
              ))}
            </div>
            <Err msg={errors['yields_t_ha']} />
          </Group>

          <Group title={t('detHistory')} hint={t('detHistoryHint')}>
            <ul className="flex flex-col gap-2">
              {form.history.map((h, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <input type="text" inputMode="numeric" aria-label={t('detYear')} value={h.year} onChange={(e) => setHist(i, { year: e.target.value })}
                    className={input + ' !w-24 shrink-0'} />
                  <select aria-label={t('detCrop')} value={h.crop_id} onChange={(e) => setHist(i, { crop_id: e.target.value })} className={input + ' flex-1 basis-40'}>
                    {CROPS.map((c) => <option key={c.id} value={c.id}>{pick(c.name, lang)}</option>)}
                  </select>
                  <button onClick={() => patch({ history: form.history.filter((_, j) => j !== i) })} aria-label={t('remove')}
                    className="px-2 py-1 text-lg text-bad hover:bg-badsoft rounded">✕</button>
                </li>
              ))}
            </ul>
            <button onClick={addHist} disabled={form.history.length >= lastYear - 1999}
              className="mt-2 rounded-lg border-2 border-dashed border-line px-3 py-2 text-sm font-semibold text-muted hover:border-leaf hover:text-leaf">
              + {t('detAddYear')}
            </button>
            <Err msg={errFor(errors, 'history')} />
          </Group>

          <Group title={t('detIrrApplied')} hint={t('detIrrAppliedHint')}>
            <div className="grid sm:grid-cols-2 gap-3">
              {crops.map((c) => (
                <Num key={c} label={cropName(c)} unit="m³/ha" value={form.irrApplied[c] ?? ''}
                  onChange={(v) => patch({ irrApplied: { ...form.irrApplied, [c]: v } })} error={errFor(errors, 'irrigation_applied_m3_ha.' + c)} />
              ))}
            </div>
            <Err msg={errors['irrigation_applied_m3_ha']} />
          </Group>
        </div>
      )}
    </section>
  )
}
