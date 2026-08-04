import {
  DEFAULT_APP_THEME,
  resolveVuetifyThemeName,
  vuetifyThemes,
  type AppThemeName,
} from '~/utils/theme/vuetifyThemes';

const THEME_CSS_VARS = [
  'primary',
  'secondary',
  'success',
  'warning',
  'error',
  'info',
  'background',
  'surface',
] as const;

/** Subset of Vuetify's active theme used for document/CSS sync (not full ThemeInstance). */
export type ThemeDocumentSync = {
  dark: boolean;
  colors: Readonly<Record<string, unknown>>;
};

function colorToCss(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

/** Sync theme colors → Tailwind `.dark` class + GDCE CSS variables. */
export function syncVuetifyThemeToDocument(theme: ThemeDocumentSync) {
  if (typeof document === 'undefined') return;

  document.documentElement.classList.toggle('dark', theme.dark);

  const root = document.documentElement.style;
  for (const key of THEME_CSS_VARS) {
    const css = colorToCss(theme.colors[key]);
    if (css) root.setProperty(`--gdce-${key}`, css);
  }

  root.setProperty('--dot-pattern-color', theme.dark ? '#e4e4e7' : '#111827');
  root.setProperty('--gdce-icon-fg', theme.dark ? '#d4d4d8' : '#374151');
  root.setProperty('--gdce-icon-muted', theme.dark ? '#a1a1aa' : '#6b7280');
  root.setProperty('--gdce-icon-subtle', theme.dark ? '#71717a' : '#9ca3af');
}

/** Sync document from static theme config (safe in Nuxt plugins — no useTheme). */
export function syncAppThemeByName(themeName: AppThemeName = DEFAULT_APP_THEME) {
  const definition = vuetifyThemes[resolveVuetifyThemeName(themeName)];
  syncVuetifyThemeToDocument({
    dark: definition.dark ?? false,
    colors: definition.colors,
  });
}
