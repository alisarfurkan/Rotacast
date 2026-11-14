import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useLang, useT } from '../ctx'
import { getZones } from '../api'
import { inGeometry } from '../geo'
import type { ZoneProps, ZonesData } from '../types'

maplibregl.setWorkerUrl(workerUrl)

export interface Point { lat: number; lon: number }
export const KONYA: Point = { lat: 37.6, lon: 32.75 }
/** Sample fields whose satellite data is already cached: they open in seconds, also offline. */
export const SAMPLES: (Point & { zone: string })[] = [
  { zone: 'central', ...KONYA },
  { zone: 'toros', lat: 36.99, lon: 32.46 },
  { zone: 'seydisehir', lat: 37.42, lon: 31.85 },
  { zone: 'beysehir', lat: 37.68, lon: 31.75 },
]
export const isSample = (p: Point | null) => !!p && SAMPLES.some((s) => Math.abs(s.lat - p.lat) < 1e-6 && Math.abs(s.lon - p.lon) < 1e-6)

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

const KONYA_BBOX = [31.26, 36.75, 34.44, 39.31] as const
const PAD = 0.5

/** Zone containing the point, or why the point is not usable. */
export function locate(z: ZonesData | null, p: Point): { zone: ZoneProps | null; problem: 'outside' | 'lake' | null } {
  if (!z) return { zone: null, problem: null }
  if (!z.boundary.features.some((f) => inGeometry(p.lon, p.lat, f.geometry))) return { zone: null, problem: 'outside' }
  if (z.lakes.features.some((f) => inGeometry(p.lon, p.lat, f.geometry))) return { zone: null, problem: 'lake' }
  const f = z.zones.features.find((x) => inGeometry(p.lon, p.lat, x.geometry))
  return { zone: f?.properties ?? null, problem: null }
}

export function FieldPicker({ point, onPick }: { point: Point | null; onPick: (p: Point) => void }) {
  const t = useT()
  const lang = useLang()
  const [zones, setZones] = useState<ZonesData | null>(null)
  const [mapReady, setMapReady] = useState(false)
  const [notice, setNotice] = useState<'outsideKonya' | 'onLake' | null>(null)
  const [hoverId, setHoverId] = useState<number | null>(null)
  const [legendOpen, setLegendOpen] = useState(() => typeof window === 'undefined' || window.innerWidth >= 640)
  const zonesRef = useRef<ZonesData | null>(null)
  zonesRef.current = zones
  useEffect(() => { getZones().then(setZones).catch(() => { /* map still works without zones */ }) }, [])
  const zname = (z: ZoneProps) => (lang === 'tr' ? z.name_tr : z.name_en)
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const marker = useRef<maplibregl.Marker | null>(null)
  const onPickRef = useRef(onPick)
  onPickRef.current = onPick
  const [base, setBase] = useState<'esri' | 'osm'>('esri')

  useEffect(() => {
    if (!el.current) return
    const [w, s, e, n] = KONYA_BBOX
    const m = new maplibregl.Map({
      container: el.current, style, bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: 10 },
      minZoom: 6, maxBounds: [[w - PAD, s - PAD], [e + PAD, n + PAD]], attributionControl: { compact: true },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => setMapReady(true))
    m.on('click', (ev) => {
      const p = { lat: +ev.lngLat.lat.toFixed(4), lon: +ev.lngLat.lng.toFixed(4) }
      const { problem } = locate(zonesRef.current, p)
      if (problem) { setNotice(problem === 'lake' ? 'onLake' : 'outsideKonya'); return }
      setNotice(null)
      onPickRef.current(p)
    })
    map.current = m
    return () => { m.remove(); map.current = null; setMapReady(false) }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !zones || m.getSource('zones')) return
    m.addSource('zones', { type: 'geojson', data: zones.zones as never })
    m.addSource('lakes', { type: 'geojson', data: zones.lakes as never })
    m.addSource('boundary', { type: 'geojson', data: zones.boundary as never })
    m.addLayer({ id: 'zones-fill', type: 'fill', source: 'zones', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.35 } })
    m.addLayer({ id: 'zones-line', type: 'line', source: 'zones', paint: { 'line-color': ['get', 'color'], 'line-width': 1, 'line-opacity': 0.9 } })
    m.addLayer({ id: 'lakes-fill', type: 'fill', source: 'lakes', paint: { 'fill-color': '#3b8fd1', 'fill-opacity': 0.75 } })
    m.addLayer({ id: 'boundary-line', type: 'line', source: 'boundary', paint: { 'line-color': '#ffffff', 'line-width': 2.5, 'line-opacity': 0.95 } })
    m.on('mousemove', 'zones-fill', (ev) => {
      const id = ev.features?.[0]?.properties?.id
      setHoverId(typeof id === 'number' ? id : null)
    })
    m.on('mouseleave', 'zones-fill', () => setHoverId(null))
  }, [mapReady, zones])

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

  const here = point ? locate(zones, point).zone : null
  const hover = hoverId != null ? zones?.zones.features.find((f) => f.properties.id === hoverId)?.properties : null
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
        {hover && (
          <div className="absolute left-2 top-11 rounded-lg bg-white/90 text-[#2b1f16] text-xs font-semibold px-2.5 py-1.5 shadow pointer-events-none flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: hover.color }} />{zname(hover)}
          </div>
        )}
        {zones && (
          <div className="absolute left-2 bottom-6 max-w-[80%] rounded-lg bg-white/90 text-[#2b1f16] text-xs shadow">
            <button onClick={() => setLegendOpen((o) => !o)} aria-expanded={legendOpen} className="px-2.5 py-1.5 font-semibold w-full text-left">
              {t('zoneLegend')} {legendOpen ? '▾' : '▸'}
            </button>
            {legendOpen && (
              <ul className="px-2.5 pb-2 flex flex-col gap-1">
                {zones.zones.features.map((f) => (
                  <li key={f.properties.id} className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: f.properties.color }} />
                    <span>{zname(f.properties)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
      {notice && <p role="alert" className="mt-2 rounded-lg bg-sunsoft border border-sun px-3 py-2 text-sm">{t(notice)}</p>}
      <div className="mt-2 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-bold text-muted">{t('samplesLabel')}</span>
          {SAMPLES.map((s) => {
            const f = zones?.zones.features.find((x) => x.properties.key === s.zone)
            return (
              <button key={s.zone} onClick={() => { setNotice(null); onPick({ lat: s.lat, lon: s.lon }) }}
                className="text-xs font-semibold rounded-full border border-line bg-surface2 hover:bg-leafsoft px-2.5 py-1 flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: f?.properties.color ?? '#888' }} />
                {f ? zname(f.properties) : s.zone}
              </button>
            )
          })}
        </div>
        <p className="text-xs text-muted tabular-nums" aria-live="polite">
          {t('coords')}: {point ? `${point.lat.toFixed(4)}°N, ${point.lon.toFixed(4)}°E` : t('noPoint')}
        </p>
      </div>
      {here && (
        <p className="text-sm mt-1.5 flex items-center gap-2">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ background: here.color }} />
          <span><span className="text-muted">{t('zoneOfPoint')}:</span> <strong>{zname(here)}</strong></span>
        </p>
      )}
      <p className="text-xs text-muted mt-1">{t('mapHint')}</p>
      {point && !isSample(point) && (
        <p className="text-xs mt-1 rounded-lg bg-surface2 px-2.5 py-1.5">⏳ {t('newPointNote')}</p>
      )}
    </div>
  )
}
