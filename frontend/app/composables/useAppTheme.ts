import { computed, watch } from 'vue';
import { useTheme } from 'vuetify';
import { useUiStore } from '~/stores/ui.store';
import { resolveVuetifyThemeName, type AppThemeName } from '~/utils/theme/vuetifyThemes';
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

  const applyResolvedTheme = (theme: AppThemeName) => {
    const resolvedTheme = resolveVuetifyThemeName(theme);
    if (vuetifyTheme.global.name.value !== resolvedTheme) {
      vuetifyTheme.change(resolvedTheme);
    }
    sync();
  };

  const applyTheme = (theme: AppThemeName) => {
    uiStore.setTheme(theme);
    applyResolvedTheme(theme);
  };

  if (!themeBridgeInitialized) {
    themeBridgeInitialized = true;

    applyResolvedTheme(uiStore.theme);

    watch(
      () => uiStore.theme,
      (themeName) => {
        applyResolvedTheme(themeName);
      },
    );

    watch(() => vuetifyTheme.global.name.value, sync);

    if (typeof window !== 'undefined') {
      const systemThemeListener = window.matchMedia('(prefers-color-scheme: dark)');
      systemThemeListener.addEventListener('change', () => {
        if (uiStore.theme === 'system') {
          applyResolvedTheme('system');
        }
      });
    }
  }

  return {
    theme: computed(() => uiStore.theme),
    isDark: computed(() => vuetifyTheme.global.current.value.dark),
    currentTheme: computed(() => vuetifyTheme.global.current.value),
    setTheme: applyTheme,
    toggleTheme: () => applyTheme(uiStore.theme === 'dark' ? 'light' : 'dark'),
  };
};
