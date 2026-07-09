import { watch } from 'vue';
import { useLocale as useVuetifyLocale } from 'vuetify';
import { normalizeAppLanguage, type AppLanguage } from '~/composables/useLanguages';

const LOCALE_STORAGE_KEY = 'app-locale';

export function useAppLocale() {
  const { locale, setLocale, t, te } = useI18n();
  const vuetifyLocale = useVuetifyLocale();

  function syncVuetifyLocale(code: string) {
    const current = vuetifyLocale?.current;
    if (!current || current.value === code) return;
    current.value = code;
  }

  function persistLocale(code: AppLanguage) {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, code);
    } catch {
      // Ignore storage write errors.
    }
  }

  function setLanguage(code: AppLanguage) {
    const normalized = normalizeAppLanguage(code);
    setLocale(normalized);
    syncVuetifyLocale(normalized);
    persistLocale(normalized);
  }

  // Keep Vuetify in sync when locale changes elsewhere (e.g. devtools).
  watch(
    locale,
    (code) => {
      syncVuetifyLocale(code);
    },
    { immediate: true },
  );

  return {
    locale,
    t,
    te,
    setLanguage,
    activeLanguage: locale,
  };
}
