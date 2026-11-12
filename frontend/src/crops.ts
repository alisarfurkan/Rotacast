import type { I18nText } from './types'

// Ids, names and categories mirror backend/rotacast/knowledge/crops.yaml (21 crops).
export type CropCategory = 'cereal' | 'legume' | 'root' | 'oilseed' | 'forage' | 'cover'

export interface Crop { id: string; name: I18nText; cat: CropCategory }

const c = (id: string, en: string, tr: string, cat: CropCategory): Crop => ({ id, name: { en, tr }, cat })

export const CROPS: Crop[] = [
  c('wheat_winter', 'Winter wheat', 'Kışlık buğday', 'cereal'),
  c('barley_winter', 'Winter barley', 'Kışlık arpa', 'cereal'),
  c('oats_spring', 'Spring oats', 'Yulaf (yazlık)', 'cereal'),
  c('rye_cover', 'Winter rye (cover crop)', 'Çavdar (örtü bitkisi)', 'cover'),
  c('sugar_beet', 'Sugar beet', 'Şeker pancarı', 'root'),
  c('maize_grain', 'Grain maize', 'Dane mısır', 'cereal'),
  c('maize_silage', 'Silage maize', 'Silajlık mısır', 'forage'),
  c('sunflower', 'Sunflower', 'Ayçiçeği', 'oilseed'),
  c('safflower', 'Safflower', 'Aspir', 'oilseed'),
  c('chickpea', 'Chickpea', 'Nohut', 'legume'),
  c('lentil', 'Lentil', 'Mercimek', 'legume'),
  c('dry_bean', 'Dry bean', 'Kuru fasulye', 'legume'),
  c('vetch_forage', 'Common vetch (forage)', 'Adi fiğ (yem)', 'forage'),
  c('vetch_cover', 'Common vetch (cover crop)', 'Adi fiğ (örtü bitkisi)', 'cover'),
  c('vetch_barley_mix', 'Vetch + barley mix (forage)', 'Fiğ + arpa karışımı (yem)', 'forage'),
  c('sainfoin', 'Sainfoin', 'Korunga', 'forage'),
  c('alfalfa', 'Alfalfa', 'Yonca', 'forage'),
  c('canola_winter', 'Winter canola', 'Kışlık kanola', 'oilseed'),
  c('potato', 'Potato', 'Patates', 'root'),
  c('sorghum', 'Grain sorghum', 'Dane sorgum', 'cereal'),
  c('soybean', 'Soybean', 'Soya', 'legume'),
]

export const CROP_BY_ID: Record<string, Crop> = Object.fromEntries(CROPS.map((x) => [x.id, x]))

// Category colours (calendar blocks). Cover crops are drawn hatched.
export const CAT_COLOR: Record<CropCategory, string> = {
  cereal: '#c9a227',
  legume: '#4f9d5d',
  root: '#b5651d',
  oilseed: '#e08e0b',
  forage: '#7fb069',
  cover: '#3f8f7a',
}
