import { computed } from 'vue';
import { useAppLocale } from '~/composables/common/useAppLocale';

export const APP_LANGUAGES = [
  { id: 'en', labelKey: 'settings.language.options.en', nativeLabel: 'English' },
  { id: 'km', labelKey: 'settings.language.options.km', nativeLabel: 'ភាសាខ្មែរ' },
] as const;

export type AppLanguage = (typeof APP_LANGUAGES)[number]['id'];

export type AppLanguageOption = {
  readonly id: AppLanguage;
  readonly nativeLabel: string;
};

export function normalizeAppLanguage(value: unknown): AppLanguage {
  return value === 'km' ? 'km' : 'en';
}

export function useLanguages() {
  const { locale, setLanguage } = useAppLocale();

  const activeLanguage = computed({
    get: () => normalizeAppLanguage(locale.value),
    set: (value: AppLanguage) => setLanguage(value),
  });

  return {
    languages: APP_LANGUAGES,
    activeLanguage,
  };
}
