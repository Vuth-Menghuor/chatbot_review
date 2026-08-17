import type { EChartsOption, ExtendedChartOutput } from './types';
import { chartColor, chartPalette } from './palette';

export function buildTreemapOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const firstSeries = out.series?.[0];
  const key = firstSeries?.key || 'value';
  const treeData =
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
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    color: chartPalette(isDark),
    series: [
      {
        name: out.title || 'Treemap',
        type: 'treemap',
        visibleMin: 300,
        label: { show: true, formatter: '{b}: {c}' },
        upperLabel: { show: true, height: 30 },
        itemStyle: { borderColor: isDark ? '#09090b' : '#ffffff' },
        data: treeData,
      },
    ],
  };
}
