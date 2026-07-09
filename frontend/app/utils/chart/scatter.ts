import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildScatterOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const seriesList =
    out.series?.map((s) => {
      const seriesData =
        out.data?.map((item) => {
          const xVal = item[out.xKey];
          const yVal = item[s.key];
          const numX = typeof xVal === 'number' ? xVal : parseFloat(String(xVal)) || 0;
          const numY = typeof yVal === 'number' ? yVal : parseFloat(String(yVal)) || 0;
          return [numX, numY];
        }) || [];
      return {
        name: s.name,
        type: 'scatter',
        data: seriesData,
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
    grid: {
      left: '3%',
      right: '4%',
      bottom: '12%',
      top: '15%',
      containLabel: true,
    },
    xAxis: {
      scale: true,
      axisLine: { lineStyle: { color: gridLineColor } },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridLineColor } },
    },
    yAxis: {
      scale: true,
      axisLine: { lineStyle: { color: gridLineColor } },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridLineColor } },
    },
    series: seriesList,
  };
}
