export const CHART_PALETTE = [
  '#2563eb',
  '#16a34a',
  '#f59e0b',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
  '#ea580c',
  '#4f46e5',
];

export const CHART_PALETTE_DARK = [
  '#60a5fa',
  '#4ade80',
  '#fbbf24',
  '#f87171',
  '#a78bfa',
  '#22d3ee',
  '#f472b6',
  '#a3e635',
  '#fb923c',
  '#818cf8',
];

export function chartPalette(isDark: boolean) {
  return isDark ? CHART_PALETTE_DARK : CHART_PALETTE;
}

export function chartColor(index: number, isDark: boolean) {
  const palette = chartPalette(isDark);
  return palette[index % palette.length];
}

export function seriesColor(configuredColor: unknown, index: number, isDark: boolean) {
  return typeof configuredColor === 'string' && configuredColor.trim()
    ? configuredColor
    : chartColor(index, isDark);
}
