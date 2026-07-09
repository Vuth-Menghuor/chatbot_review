import type { ThemeDefinition } from 'vuetify';

export const APP_THEME_NAMES = ['light', 'dark', 'custom'] as const;

export type AppThemeName = (typeof APP_THEME_NAMES)[number];

export const DEFAULT_APP_THEME: AppThemeName = 'light';

export const vuetifyThemes = {
  light: {
    dark: false,
    colors: {
      primary: '#1b5875',
      secondary: '#0284c7',
      success: '#16a34a',
      warning: '#f59e0b',
      error: '#e11d48',
      info: '#0891b2',
      background: '#ffffff',
      surface: '#ffffff',
    },
  },
  dark: {
    dark: true,
    colors: {
      primary: '#38bdf8',
      secondary: '#0284c7',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#fb7185',
      info: '#06b6d4',
      background: '#09090b',
      surface: '#18181b',
    },
  },
  custom: {
    dark: false,
    colors: {
      primary: '#6d5dfc',
      secondary: '#0f766e',
      success: '#15803d',
      warning: '#d97706',
      error: '#dc2626',
      info: '#2563eb',
      background: '#f7f3ea',
      surface: '#fffaf0',
    },
  },
} satisfies Record<AppThemeName, ThemeDefinition>;

export function isAppThemeName(value: unknown): value is AppThemeName {
  return typeof value === 'string' && APP_THEME_NAMES.includes(value as AppThemeName);
}
