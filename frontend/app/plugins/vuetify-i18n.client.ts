import { useI18n } from 'vue-i18n';
import type { Composer } from 'vue-i18n';
import { createVueI18nAdapter } from 'vuetify/locale/adapters/vue-i18n';

const LOCALE_STORAGE_KEY = 'app-locale';

/** @nuxtjs/i18n exposes the global composer on `$i18n`, not the full vue-i18n instance. */
function getLocaleCode(composer: Composer): string {
  const { locale } = composer;
  return typeof locale === 'string' ? locale : locale.value;
}

export default defineNuxtPlugin({
  name: 'vuetify-i18n',
  dependsOn: ['i18n:plugin'],
  setup(nuxtApp) {
    const composer = nuxtApp.$i18n as Composer | undefined;
    if (!composer) return;

    try {
      const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
      if (saved === 'en' || saved === 'km') {
        composer.locale.value = saved;
      }
    } catch {
      // Ignore storage read errors.
    }

    nuxtApp.hook('vuetify:configuration', ({ vuetifyOptions }) => {
      const global = nuxtApp.$i18n as Composer | undefined;
      if (!global?.locale) return;

      vuetifyOptions.locale = {
        ...vuetifyOptions.locale,
        locale: getLocaleCode(global),
        fallback: 'en',
        adapter: createVueI18nAdapter({
          i18n: { global },
          useI18n,
        }),
      };
    });
  },
});
