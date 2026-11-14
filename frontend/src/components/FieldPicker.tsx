import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useT } from '../ctx'

maplibregl.setWorkerUrl(workerUrl)

export interface Point { lat: number; lon: number }
export const KONYA: Point = { lat: 37.6, lon: 32.75 }

export const style: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    esri: {
      type: 'raster', tileSize: 256, maxzoom: 19,
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    },
    osm: {
      type: 'raster', tileSize: 256, maxzoom: 19,
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    { id: 'esri', type: 'raster', source: 'esri' },
    { id: 'osm', type: 'raster', source: 'osm', layout: { visibility: 'none' } },
  ],
}

export function FieldPicker({ point, onPick }: { point: Point | null; onPick: (p: Point) => void }) {
  const t = useT()
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const marker = useRef<maplibregl.Marker | null>(null)
  const onPickRef = useRef(onPick)
  onPickRef.current = onPick
  const [base, setBase] = useState<'esri' | 'osm'>('esri')

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({ container: el.current, style, center: [32.75, 38.2], zoom: 5.2, attributionControl: { compact: true } })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('click', (e) => onPickRef.current({ lat: +e.lngLat.lat.toFixed(4), lon: +e.lngLat.lng.toFixed(4) }))
    map.current = m
    return () => { m.remove(); map.current = null }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return
    const apply = () => {
      m.setLayoutProperty('esri', 'visibility', base === 'esri' ? 'visible' : 'none')
      m.setLayoutProperty('osm', 'visibility', base === 'osm' ? 'visible' : 'none')
    }
    if (m.isStyleLoaded()) apply(); else m.once('load', apply)
  }, [base])

  useEffect(() => {
    const m = map.current
    if (!m || !point) return
    if (!marker.current) {
      const node = document.createElement('div')
      node.innerHTML = '<div style="width:22px;height:22px;border-radius:50%;background:#f2c14e;border:3px solid #3b2616;box-shadow:0 0 0 6px rgba(242,193,78,.35)"></div>'
      marker.current = new maplibregl.Marker({ element: node }).setLngLat([point.lon, point.lat]).addTo(m)
    } else marker.current.setLngLat([point.lon, point.lat])
    const z = m.getZoom()
    if (z < 9) m.flyTo({ center: [point.lon, point.lat], zoom: 11, duration: 1400 })
  }, [point])

  const fly = () => onPick(KONYA)
  return (
    <div>
      <div className="relative rounded-2xl overflow-hidden border border-line">
        <div ref={el} className="h-64 md:h-80 lg:h-[26rem] w-full" aria-label={t('mapHint')} />
        <div className="absolute left-2 top-2 flex rounded-lg overflow-hidden text-xs font-semibold shadow bg-white/90 text-[#2b1f16]">
          {(['esri', 'osm'] as const).map((b) => (
            <button key={b} onClick={() => setBase(b)} aria-pressed={base === b}
              className={'px-2.5 py-1.5 ' + (base === b ? 'bg-[#3b2616] text-white' : '')}>
              {b === 'esri' ? t('satellite') : t('streets')}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 flex-wrap">
        <button onClick={fly} className="text-sm font-semibold rounded-full border border-line bg-surface2 hover:bg-leafsoft px-3 py-1.5">
          📍 {t('konyaDemo')}
        </button>
        <p className="text-xs text-muted tabular-nums" aria-live="polite">
          {t('coords')}: {point ? `${point.lat.toFixed(4)}°N, ${point.lon.toFixed(4)}°E` : t('noPoint')}
        </p>
      </div>
      <p className="text-xs text-muted mt-1">{t('mapHint')}</p>
    </div>
  )
}
