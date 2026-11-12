import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, HeatmapChart, LineChart, ScatterChart, GridComponent, LegendComponent, MarkAreaComponent,
  MarkLineComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

export type EOption = echarts.EChartsCoreOption

export function useCssVar(name: string): string {
  const [v, setV] = useState(() => getComputedStyle(document.documentElement).getPropertyValue(name).trim())
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const f = () => setV(getComputedStyle(document.documentElement).getPropertyValue(name).trim())
    mq.addEventListener('change', f)
    return () => mq.removeEventListener('change', f)
  }, [name])
  return v
}

export function Chart({ option, height, label }: { option: EOption; height: number; label: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const inst = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    if (!ref.current) return
    const c = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    inst.current = c
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); c.dispose(); inst.current = null }
  }, [])
  useEffect(() => { inst.current?.setOption(option, true) }, [option])
  return <div ref={ref} role="img" aria-label={label} style={{ height, width: '100%' }} />
}
