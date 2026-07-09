import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildSunburstOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    series: [
      {
        type: 'sunburst',
        data: out.data || [],
        radius: [0, '90%'],
        label: { rotate: 'radial', color: textColor },
      },
    ],
  };
}
