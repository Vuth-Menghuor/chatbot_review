/** Translate from script context (stores, utils) where `useI18n()` is unavailable. */
export function tApp(key: string, fallback?: string): string {
  if (import.meta.server) {
    return fallback ?? key;
  }

  try {
    const { $i18n } = useNuxtApp();
    const result = $i18n.t(key);
    return typeof result === 'string' ? result : (fallback ?? key);
  } catch {
    return fallback ?? key;
  }
}
