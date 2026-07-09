import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildRadarOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const categories = out.data?.map((item) => String(item[out.xKey] ?? '')) || [];

  const indicators = categories.map((cat) => {
    let maxVal = 100;
    out.series?.forEach((s) => {
      const item = out.data?.find((d) => String(d[out.xKey]) === cat);
      if (item) {
        const val = Number(item[s.key] ?? 0);
        if (val > maxVal) maxVal = val;
      }
    });
    return { name: cat, max: Math.ceil(maxVal * 1.1) };
  });

  const radarSeriesData =
    out.series?.map((s) => {
      const vals = categories.map((cat) => {
        const item = out.data?.find((d) => String(d[out.xKey]) === cat);
        return Number(item?.[s.key] ?? 0);
      });
      return {
        value: vals,
        name: s.name,
        itemStyle: { color: s.color },
      };
    }) || [];

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
    legend: {
      orient: 'horizontal',
      bottom: '0%',
      left: 'center',
      textStyle: { color: textColor },
    },
    radar: {
      indicator: indicators,
      axisName: { color: textColor },
      splitArea: { show: false },
    },
    series: [
      {
        name: out.title || 'Radar',
        type: 'radar',
        data: radarSeriesData,
      },
    ],
  };
}
