import { createContext, useContext } from 'react'
import type { Lang } from './types'
import { translate, type Key } from './i18n'

export const LangContext = createContext<Lang>('tr')
export const useLang = () => useContext(LangContext)
export function useT() {
  const lang = useLang()
  return (key: Key, vars?: Record<string, string | number>) => translate(lang, key, vars)
}
