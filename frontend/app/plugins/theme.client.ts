import { useUiStore } from '~/stores/ui.store';
import { isAppThemeName } from '~/utils/theme/vuetifyThemes';
import { syncAppThemeByName } from '~/utils/theme/syncVuetifyThemeToDocument';
import { readString, storageKeys } from '~/utils/storage';

/** Restore saved theme before paint. Do not call useTheme() here — Vuetify requires setup(). */
export default defineNuxtPlugin(() => {
  const uiStore = useUiStore();
  const savedTheme = readString(storageKeys.appTheme);

  if (isAppThemeName(savedTheme)) {
    uiStore.theme = savedTheme;
  }

  syncAppThemeByName(uiStore.theme);
});
