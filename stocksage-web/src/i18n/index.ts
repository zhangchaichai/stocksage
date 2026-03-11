import { create } from 'zustand';
import en from './locales/en';
import zh from './locales/zh';
import type { Translations } from './locales/en';

type Locale = 'en' | 'zh';

const locales: Record<Locale, Translations> = { en, zh };

interface I18nState {
  locale: Locale;
  t: Translations;
  setLocale: (locale: Locale) => void;
}

const getInitialLocale = (): Locale => {
  const saved = localStorage.getItem('stocksage_locale');
  if (saved === 'en' || saved === 'zh') return saved;
  return navigator.language.startsWith('zh') ? 'zh' : 'en';
};

export const useI18n = create<I18nState>((set) => {
  const initial = getInitialLocale();
  return {
    locale: initial,
    t: locales[initial],
    setLocale: (locale: Locale) => {
      localStorage.setItem('stocksage_locale', locale);
      set({ locale, t: locales[locale] });
    },
  };
});
