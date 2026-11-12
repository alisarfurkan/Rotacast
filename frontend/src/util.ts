import type { I18nText, Lang } from './types'

export const pick = (t: I18nText | undefined, lang: Lang) => (t ? t[lang] || t.en : '')

export const fmt = (n: number, d = 0, lang: Lang = 'en') =>
  n.toLocaleString(lang === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: d, maximumFractionDigits: d })

export const signed = (n: number, d = 0, lang: Lang = 'en') => (n > 0 ? '+' : n < 0 ? '−' : '') + fmt(Math.abs(n), d, lang)

const MD = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
export function mdToDoy(md: string): number {
  const [m, d] = md.split('-').map(Number)
  return MD.slice(0, m - 1).reduce((s, x) => s + x, 0) + d
}
export function doyToMonthDay(doy: number, lang: Lang): string {
  let m = 0, d = Math.round(doy)
  while (m < 11 && d > MD[m]) { d -= MD[m]; m++ }
  const names = lang === 'tr'
    ? ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']
    : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return lang === 'tr' ? `${d} ${names[m]}` : `${names[m]} ${d}`
}
export function doyToMonthName(doy: number, lang: Lang): string {
  return doyToMonthDay(doy, lang).replace(/\d+/g, '').trim()
}
export const monthNames = (lang: Lang) =>
  lang === 'tr'
    ? ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']
    : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const to100 = (v: number, all: number[]) => (Math.max(...all) <= 1 ? v * 100 : v)

/** "early Dec" / "Aralık başı": rough position in a month. */
export function fuzzyDoy(doy: number, lang: Lang): string {
  let m = 0, d = Math.max(1, Math.round(doy))
  while (m < 11 && d > MD[m]) { d -= MD[m]; m++ }
  const part = d <= 10 ? 0 : d <= 20 ? 1 : 2
  if (lang === 'tr') {
    const names = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
    return `${names[m]} ${['başı', 'ortası', 'sonu'][part]}`
  }
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${['early', 'mid', 'late'][part]} ${names[m]}`
}

const UNIT_TR: Record<string, string> = {
  days: 'gün', 'days/yr': 'gün/yıl', 'day': 'gün', '°C·day': '°C·gün', years: 'yıl', 'm3/ha/yr': 'm³/ha/yıl', 'USD/ha/yr': 'USD/ha/yıl',
  'kg/ha/yr': 'kg/ha/yıl', C: '°C', probability: 'olasılık', ratio: 'oran', fraction: 'oran', doy: '',
}
export function unitLabel(u: string, lang: Lang): string {
  if (u === 'C') return '°C'
  if (lang === 'tr') return UNIT_TR[u] ?? u.replace('m3', 'm³').replace('/yr', '/yıl')
  return u.replace('m3', 'm³')
}
