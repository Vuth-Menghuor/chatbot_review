import type { EChartsOption, ExtendedChartOutput } from './types';
import { chartColor, chartPalette } from './palette';

export function buildFunnelOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const firstSeries = out.series?.[0];
  const key = firstSeries?.key || 'value';
  const funnelData =
    out.data?.map((item, index) => ({
      name: String(item[out.xKey] ?? ''),
      value: Number(item[key] ?? 0),
      itemStyle: { color: chartColor(index, isDark) },
    })) || [];

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b} : {c}',
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    legend: {
      orient: 'horizontal',
      bottom: '0%',
      left: 'center',
      textStyle: { color: textColor },
    },
    color: chartPalette(isDark),
    series: [
      {
        name: out.title || 'Funnel',
        type: 'funnel',
        left: '10%',
        top: 60,
        bottom: 60,
        width: '80%',
        min: 0,
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside' },
        data: funnelData,
      },
    ],
  };
}
