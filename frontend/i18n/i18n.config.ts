import en from './locales/en.json';
import km from './locales/km.json';
import { en as vuetifyEn, km as vuetifyKm } from 'vuetify/locale';

export default defineI18nConfig(() => ({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: {
    en: {
      ...en,
      $vuetify: vuetifyEn,
    },
    km: {
      ...km,
      $vuetify: vuetifyKm,
    },
  },
}));
