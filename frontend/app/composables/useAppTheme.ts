import { computed, watch } from 'vue';
import { useTheme } from 'vuetify';
import { useUiStore } from '~/stores/ui.store';
import type { AppThemeName } from '~/utils/theme/vuetifyThemes';
import { syncVuetifyThemeToDocument } from '~/utils/theme/syncVuetifyThemeToDocument';

let themeBridgeInitialized = false;

/**
 * Bridges Pinia theme state ↔ Vuetify useTheme().
 * Must run inside a component setup (e.g. app.vue), not in a Nuxt plugin.
 */
export const useAppTheme = () => {
  const vuetifyTheme = useTheme();
  const uiStore = useUiStore();

  const sync = () => {
    const current = vuetifyTheme.global.current.value;
    syncVuetifyThemeToDocument({ dark: current.dark, colors: current.colors });
  };

  const applyTheme = (theme: AppThemeName) => {
    uiStore.setTheme(theme);
    vuetifyTheme.change(theme);
    sync();
  };

  if (!themeBridgeInitialized) {
    themeBridgeInitialized = true;

    if (vuetifyTheme.global.name.value !== uiStore.theme) {
      vuetifyTheme.change(uiStore.theme);
    }
    sync();

    watch(
      () => uiStore.theme,
      (themeName) => {
        if (vuetifyTheme.global.name.value !== themeName) {
          vuetifyTheme.change(themeName);
        }
        sync();
      },
    );

    watch(() => vuetifyTheme.global.name.value, sync);
  }

  return {
    theme: computed(() => uiStore.theme),
    isDark: computed(() => vuetifyTheme.global.current.value.dark),
    currentTheme: computed(() => vuetifyTheme.global.current.value),
    setTheme: applyTheme,
    toggleTheme: () => applyTheme(uiStore.theme === 'dark' ? 'light' : 'dark'),
  };
};
