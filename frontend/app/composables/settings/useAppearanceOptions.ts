import { computed } from 'vue';
import { MonitorIcon, MoonIcon, SunIcon } from 'lucide-vue-next';
import type { AppThemeName } from '~/utils/theme/vuetifyThemes';

const THEME_IDS = ['light', 'dark', 'system'] as const satisfies readonly AppThemeName[];

const THEME_ICONS = {
  light: SunIcon,
  dark: MoonIcon,
  system: MonitorIcon,
} as const;

const THEME_SWATCHES: Record<AppThemeName, string[]> = {
  light: ['#1b5875', '#0284c7', '#ffffff'],
  dark: ['#38bdf8', '#18181b', '#09090b'],
  system: ['#1b5875', '#18181b', '#ffffff'],
};

export function useAppearanceOptions() {
  const { t } = useI18n();

  const appearanceOptions = computed(() =>
    THEME_IDS.map((value) => ({
      value,
      label: t(`settings.appearance.options.${value}.label`),
      description: t(`settings.appearance.options.${value}.description`),
      icon: THEME_ICONS[value],
      swatches: THEME_SWATCHES[value],
    })),
  );

  return { appearanceOptions };
}
