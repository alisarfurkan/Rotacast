import { FieldPicker, type Point } from './FieldPicker'
import { CROPS, CROP_BY_ID } from '../crops'
import { useLang, useT } from '../ctx'
import { pick } from '../util'
import type { Irrigation, Priorities, RotationStep, WaterAccess } from '../types'
import type { Key } from '../i18n'

export interface Scenario { delta_t_c: number; precip_change_pct: number }

const PRIO: { k: keyof Priorities; label: Key; color: string }[] = [
  { k: 'water', label: 'pWater', color: 'var(--water)' },
  { k: 'soil', label: 'pSoil', color: '#8a5a2b' },
  { k: 'income', label: 'pIncome', color: 'var(--sun)' },
  { k: 'erosion', label: 'pErosion', color: '#7c6a58' },
  { k: 'risk', label: 'pRisk', color: 'var(--leaf)' },
]

export function redistribute(p: Priorities, k: keyof Priorities, v: number): Priorities {
  const keys = Object.keys(p) as (keyof Priorities)[]
  const others = keys.filter((x) => x !== k)
  const rest = 1 - v
  const sum = others.reduce((s, x) => s + p[x], 0)
  const out = { ...p, [k]: v }
  for (const x of others) out[x] = sum > 0 ? (p[x] / sum) * rest : rest / others.length
  return out
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-4 md:p-5">
      <h2 className="font-display text-lg font-extrabold mb-3 text-soil">{title}</h2>
      {children}
    </section>
  )
}

interface Props {
  point: Point | null
  onPick: (p: Point) => void
  rotation: RotationStep[]
  setRotation: (r: RotationStep[]) => void
  waterAccess: WaterAccess
  setWaterAccess: (w: WaterAccess) => void
  priorities: Priorities
  setPriorities: (p: Priorities) => void
  scenario: Scenario
  setScenario: (s: Scenario) => void
  onAnalyze: () => void
  loading: boolean
  error: string | null
}

export function InputPanel(p: Props) {
  const t = useT()
  const lang = useLang()
  const set = (i: number, patch: Partial<RotationStep>) =>
    p.setRotation(p.rotation.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= p.rotation.length) return
    const r = [...p.rotation]
    ;[r[i], r[j]] = [r[j], r[i]]
    p.setRotation(r)
  }
  const irrOpts: [Irrigation, Key][] = [['none', 'irrNone'], ['limited', 'irrLimited'], ['full', 'irrFull']]
  const waterOpts: [WaterAccess, Key][] = [['none', 'waterNone'], ['limited', 'waterLimited'], ['full', 'waterFull']]
  const canGo = !!p.point && p.rotation.length > 0

  return (
    <div className="flex flex-col gap-4">
      <Section title={t('step1')}>
        <FieldPicker point={p.point} onPick={p.onPick} />
      </Section>

      <Section title={t('step2')}>
        <p className="text-xs text-muted mb-3">{t('rotationHelp')}</p>
        <ol className="flex flex-col gap-2">
          {p.rotation.map((s, i) => (
            <li key={i} className="rounded-xl border border-line bg-surface2 p-2.5">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 shrink-0 rounded-full bg-soil text-bg text-xs font-bold grid place-items-center">{i + 1}</span>
                <select aria-label={`${t('year')} ${i + 1}`} value={s.crop_id} onChange={(e) => set(i, { crop_id: e.target.value })}
                  className="flex-1 min-w-0 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm">
                  {CROPS.map((c) => <option key={c.id} value={c.id}>{pick(c.name, lang)}</option>)}
                </select>
                <button onClick={() => move(i, -1)} aria-label={t('moveUp')} className="px-1.5 text-muted hover:text-ink disabled:opacity-30" disabled={i === 0}>↑</button>
                <button onClick={() => move(i, 1)} aria-label={t('moveDown')} className="px-1.5 text-muted hover:text-ink disabled:opacity-30" disabled={i === p.rotation.length - 1}>↓</button>
                <button onClick={() => p.setRotation(p.rotation.filter((_, j) => j !== i))} aria-label={t('remove')}
                  className="px-1.5 text-bad hover:bg-badsoft rounded disabled:opacity-30" disabled={p.rotation.length === 1}>✕</button>
              </div>
              <div className="mt-2 flex gap-1" role="group" aria-label={pick(CROP_BY_ID[s.crop_id]?.name, lang)}>
                {irrOpts.map(([v, k]) => (
                  <button key={v} onClick={() => set(i, { irrigation: v })} aria-pressed={s.irrigation === v}
                    className={'flex-1 text-[11px] font-semibold rounded-md py-1 border ' + (s.irrigation === v
                      ? (v === 'none' ? 'bg-sunsoft border-sun text-sun' : 'bg-watersoft border-water text-water')
                      : 'border-line text-muted hover:bg-surface')}>
                    {v !== 'none' ? '💧 ' : '☁ '}{t(k)}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ol>
        <button onClick={() => p.setRotation([...p.rotation, { crop_id: 'wheat_winter', irrigation: 'none' }])}
          disabled={p.rotation.length >= 8}
          className="mt-3 w-full rounded-xl border-2 border-dashed border-line py-2 text-sm font-semibold text-muted hover:border-leaf hover:text-leaf">
          + {t('addCrop')}
        </button>
        <fieldset className="mt-4">
          <legend className="text-sm font-semibold mb-1.5">{t('waterAccess')}</legend>
          <div className="flex gap-1">
            {waterOpts.map(([v, k]) => (
              <button key={v} onClick={() => p.setWaterAccess(v)} aria-pressed={p.waterAccess === v}
                className={'flex-1 rounded-lg py-1.5 text-sm font-semibold border ' + (p.waterAccess === v ? 'bg-water text-bg border-water' : 'border-line hover:bg-surface2')}>
                {t(k)}
              </button>
            ))}
          </div>
        </fieldset>
      </Section>

      <Section title={t('step3')}>
        <div className="flex flex-col gap-3">
          {PRIO.map(({ k, label, color }) => (
            <label key={k} className="block">
              <span className="flex justify-between text-sm font-medium">
                <span>{t(label)}</span>
                <span className="tabular-nums font-bold" style={{ color }}>{Math.round(p.priorities[k] * 100)}%</span>
              </span>
              <input type="range" min={0} max={100} value={Math.round(p.priorities[k] * 100)}
                onChange={(e) => p.setPriorities(redistribute(p.priorities, k, +e.target.value / 100))}
                className="w-full" style={{ accentColor: color }} />
            </label>
          ))}
        </div>
        <p className="text-xs text-muted mt-2">{t('prioHint')}</p>
      </Section>

      <Section title={t('step4')}>
        <label className="block mb-3">
          <span className="flex justify-between text-sm font-medium">
            <span>{t('dT')}</span>
            <span className="tabular-nums font-bold text-bad">+{p.scenario.delta_t_c.toFixed(1)} °C</span>
          </span>
          <input type="range" min={0} max={3} step={0.5} value={p.scenario.delta_t_c}
            onChange={(e) => p.setScenario({ ...p.scenario, delta_t_c: +e.target.value })} className="w-full" style={{ accentColor: 'var(--bad)' }} />
        </label>
        <label className="block">
          <span className="flex justify-between text-sm font-medium">
            <span>{t('dP')}</span>
            <span className="tabular-nums font-bold text-water">{p.scenario.precip_change_pct > 0 ? '+' : p.scenario.precip_change_pct < 0 ? '−' : ''}{Math.abs(p.scenario.precip_change_pct)}%</span>
          </span>
          <input type="range" min={-30} max={10} step={5} value={p.scenario.precip_change_pct}
            onChange={(e) => p.setScenario({ ...p.scenario, precip_change_pct: +e.target.value })} className="w-full" style={{ accentColor: 'var(--water)' }} />
        </label>
        <p className="text-xs text-muted mt-2">{t('scenarioHint')}</p>
      </Section>

      <div className="sticky bottom-3 z-10">
        <button onClick={p.onAnalyze} disabled={p.loading || !canGo} className="btn-primary w-full py-3.5 text-base shadow-lg">
          {p.loading ? t('analyzing') : t('analyze')}
        </button>
        {!p.point && <p className="text-xs text-bad mt-1 text-center bg-surface rounded">{t('needPoint')}</p>}
        {p.error && <p className="text-xs text-bad mt-1 text-center bg-surface rounded">{p.error}</p>}
      </div>
    </div>
  )
}
