import type { I18nText } from './types'

export type CropCategory = 'cereal' | 'legume' | 'root' | 'oilseed' | 'forage' | 'cover' | 'row'

export interface Crop { id: string; name: I18nText; cat: CropCategory }

export const CROPS: Crop[] = [
  { id: 'wheat_winter', name: { en: 'Winter wheat', tr: 'Kışlık buğday' }, cat: 'cereal' },
  { id: 'barley_winter', name: { en: 'Winter barley', tr: 'Kışlık arpa' }, cat: 'cereal' },
  { id: 'sugar_beet', name: { en: 'Sugar beet', tr: 'Şeker pancarı' }, cat: 'root' },
  { id: 'maize_grain', name: { en: 'Grain maize', tr: 'Dane mısır' }, cat: 'row' },
  { id: 'maize_silage', name: { en: 'Silage maize', tr: 'Silajlık mısır' }, cat: 'row' },
  { id: 'sunflower', name: { en: 'Sunflower', tr: 'Ayçiçeği' }, cat: 'oilseed' },
  { id: 'safflower', name: { en: 'Safflower', tr: 'Aspir' }, cat: 'oilseed' },
  { id: 'chickpea', name: { en: 'Chickpea', tr: 'Nohut' }, cat: 'legume' },
  { id: 'lentil', name: { en: 'Lentil', tr: 'Mercimek' }, cat: 'legume' },
  { id: 'dry_bean', name: { en: 'Dry bean', tr: 'Kuru fasulye' }, cat: 'legume' },
  { id: 'vetch_forage', name: { en: 'Vetch (forage)', tr: 'Fiğ (yem)' }, cat: 'forage' },
  { id: 'vetch_cover', name: { en: 'Vetch (cover crop)', tr: 'Fiğ (örtü bitkisi)' }, cat: 'cover' },
  { id: 'vetch_barley_mix', name: { en: 'Vetch + barley mix', tr: 'Fiğ + arpa karışımı' }, cat: 'forage' },
  { id: 'sainfoin', name: { en: 'Sainfoin', tr: 'Korunga' }, cat: 'forage' },
  { id: 'alfalfa', name: { en: 'Alfalfa', tr: 'Yonca' }, cat: 'forage' },
  { id: 'rye_cover', name: { en: 'Rye (cover crop)', tr: 'Çavdar (örtü bitkisi)' }, cat: 'cover' },
  { id: 'canola_winter', name: { en: 'Winter canola', tr: 'Kışlık kolza' }, cat: 'oilseed' },
  { id: 'potato', name: { en: 'Potato', tr: 'Patates' }, cat: 'root' },
  { id: 'sorghum', name: { en: 'Sorghum', tr: 'Sorgum' }, cat: 'row' },
  { id: 'soybean', name: { en: 'Soybean', tr: 'Soya' }, cat: 'legume' },
]

export const CROP_BY_ID: Record<string, Crop> = Object.fromEntries(CROPS.map((c) => [c.id, c]))

// Category colours (calendar blocks). Cover crops are drawn hatched.
export const CAT_COLOR: Record<CropCategory, string> = {
  cereal: '#c9a227',
  legume: '#4f9d5d',
  root: '#b5651d',
  oilseed: '#e08e0b',
  forage: '#7fb069',
  cover: '#3f8f7a',
  row: '#8c5a2b',
}
