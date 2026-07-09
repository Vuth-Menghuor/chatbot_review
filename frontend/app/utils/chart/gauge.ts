import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildGaugeOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const firstSeries = out.series?.[0];
  const key = firstSeries?.key || 'value';
  const val = Number(out.data?.[0]?.[key] ?? 0);

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      formatter: '{a} <br/>{b} : {c}%',
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    series: [
      {
        name: firstSeries?.name || out.title || 'Indicator',
        type: 'gauge',
        detail: { formatter: '{value}', color: textColor },
        data: [{ value: val, name: firstSeries?.name || '' }],
        axisLabel: { color: textColor },
      },
    ],
  };
}
