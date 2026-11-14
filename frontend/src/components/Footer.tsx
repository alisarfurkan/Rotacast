import type { FieldReport } from '../types'
import { useLang, useT } from '../ctx'
import { pick } from '../util'

const DEFAULT_SOURCES = [
  { id: 'nasa_power', name: 'NASA POWER', detail: 'Daily weather & solar', url: 'https://power.larc.nasa.gov/' },
  { id: 'nasa_modis', name: 'NASA MODIS MOD13Q1', detail: 'NDVI 250 m, 16-day', url: 'https://lpdaac.usgs.gov/products/mod13q1v061/' },
  { id: 'srtm_terrain_tiles', name: 'SRTM (AWS terrain tiles)', detail: 'Elevation & slope', url: 'https://registry.opendata.aws/terrain-tiles/' },
  { id: 'soilgrids', name: 'ISRIC SoilGrids', detail: 'Soil properties', url: 'https://soilgrids.org/' },
]

export function Footer({ report }: { report: FieldReport | null }) {
  const t = useT()
  const lang = useLang()
  const sources = report?.sources?.length ? report.sources : DEFAULT_SOURCES
  const disclaimer = report ? pick(report.disclaimer, lang) : t('supportNote')
  return (
    <footer className="mt-12 text-bg" style={{ background: '#2e2015', color: '#eadfca' }}>
      <div className="mx-auto max-w-[1500px] px-4 md:px-8 py-8 grid md:grid-cols-3 gap-6 text-sm">
        <div>
          <h2 className="font-display text-lg font-extrabold mb-2">{t('ftSources')}</h2>
          <ul className="flex flex-col gap-1.5">
            {sources.map((s) => (
              <li key={s.id}><a className="underline decoration-dotted hover:text-white" href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                <span className="opacity-70"> — {s.detail}</span></li>
            ))}
            <li className="opacity-70 text-xs mt-1">Esri World Imagery, OpenStreetMap, MapLibre GL JS, Apache ECharts.</li>
          </ul>
        </div>
        <div>
          <h2 className="font-display text-lg font-extrabold mb-2">{t('ftDisclaimerTitle')}</h2>
          <p className="leading-snug">{disclaimer}</p>
          <p className="leading-snug mt-2 opacity-90">{t('supportNote')}</p>
        </div>
        <div>
          <p className="leading-snug">{t('ftSI')}</p>
          <p className="mt-3 opacity-80">{t('ftLicense')}</p>
          <p className="mt-1 opacity-80">{t('ftBuilt')}</p>
        </div>
      </div>
    </footer>
  )
}
