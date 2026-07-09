import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildCandlestickOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const categories = out.data?.map((item) => String(item[out.xKey] ?? '')) || [];
  const rawData =
    out.data?.map((item) => {
      const open = Number(item.open ?? item.Open ?? 0);
      const close = Number(item.close ?? item.Close ?? 0);
      const lowest = Number(item.lowest ?? item.low ?? item.Low ?? 0);
      const highest = Number(item.highest ?? item.high ?? item.High ?? 0);
      return [open, close, lowest, highest];
    }) || [];

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    grid: { left: '10%', right: '10%', bottom: '15%' },
    xAxis: {
      type: 'category',
      data: categories,
      axisLine: { lineStyle: { color: gridLineColor } },
      axisLabel: { color: textColor },
    },
    yAxis: {
      scale: true,
      axisLine: { lineStyle: { color: gridLineColor } },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridLineColor } },
    },
    series: [
      {
        type: 'candlestick',
        data: rawData,
        itemStyle: {
          color: '#ef4444',
          color0: '#22c55e',
          borderColor: '#ef4444',
          borderColor0: '#22c55e',
        },
      },
    ],
  };
}
