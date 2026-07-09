import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildPieOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';
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

  const pieColors = out.series?.map((s) => s.color).filter(Boolean) || [];

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
      bottom: '0%',
      left: 'center',
      textStyle: { color: textColor },
    },
    color: pieColors.length ? pieColors : undefined,
    series: [
      {
        name: out.title || 'Data',
        type: 'pie',
        radius: chartType === 'donut' ? ['45%', '70%'] : ['0%', '70%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 8,
          borderColor: isDark ? '#09090b' : '#ffffff',
          borderWidth: 2,
        },
        label: {
          show: false,
          position: 'center',
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '14',
            fontWeight: 'bold',
          },
        },
        data: pieData,
      },
    ],
  };
}
