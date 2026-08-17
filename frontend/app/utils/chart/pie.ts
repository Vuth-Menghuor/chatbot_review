import type { EChartsOption, ExtendedChartOutput } from './types';
import { chartPalette } from './palette';

export function buildPieOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';
  const mutedTextColor = isDark ? '#a1a1aa' : '#52525b';
  const chartType = String(out.chartType || 'pie').toLowerCase();

  const firstSeries = out.series?.[0];
  const firstSeriesKey = firstSeries?.key || 'value';

  const pieData =
    out.data?.map((item) => {
      const name = String(item[out.xKey] ?? '');
      const rawVal = item[firstSeriesKey];
      const value = typeof rawVal === 'number' ? rawVal : parseFloat(String(rawVal || '0')) || 0;
      return { value, name };
    }) || [];

  const configuredColors = out.series?.map((s) => s.color).filter(Boolean) || [];
  const fallbackPalette = chartPalette(isDark);
  const pieColors =
    configuredColors.length >= pieData.length
      ? configuredColors
      : pieData.map((_, index) => configuredColors[index] || fallbackPalette[index % fallbackPalette.length]);

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)',
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      borderWidth: 1,
      textStyle: { color: textColor },
    },
    legend: {
      orient: 'horizontal',
      type: pieData.length > 8 ? 'scroll' : 'plain',
      bottom: '0%',
      left: 'center',
      icon: 'roundRect',
      itemWidth: 18,
      itemHeight: 10,
      textStyle: { color: textColor },
    },
    color: pieColors,
    series: [
      {
        name: out.title || 'Data',
        type: 'pie',
        radius: chartType === 'donut' ? ['42%', '64%'] : ['0%', '62%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: isDark ? '#09090b' : '#ffffff',
          borderWidth: 2,
        },
        label: {
          show: true,
          position: 'outside',
          formatter: '{b}\n{d}%',
          color: textColor,
          fontSize: 12,
          lineHeight: 16,
          overflow: 'truncate',
          width: 110,
        },
        labelLine: {
          show: true,
          length: 14,
          length2: 10,
          lineStyle: { color: mutedTextColor },
        },
        emphasis: {
          scale: true,
          scaleSize: 6,
          label: {
            show: true,
            fontSize: 13,
            fontWeight: 'bold',
          },
        },
        data: pieData,
      },
    ],
  };
}
