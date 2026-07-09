import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildHeatmapOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const categories = out.data?.map((item) => String(item[out.xKey] ?? '')) || [];
  const xCats = out.xCategories || categories;
  const yCats = out.yCategories || [];
  const valData =
    out.data?.map((item) => {
      const xIdx = Number(item.x ?? 0);
      const yIdx = Number(item.y ?? 0);
      const val = Number(item.value ?? item.val ?? 0);
      return [xIdx, yIdx, val];
    }) || [];

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      position: 'top',
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    grid: { height: '50%', top: '15%' },
    xAxis: {
      type: 'category',
      data: xCats,
      splitArea: { show: true },
      axisLabel: { color: textColor },
    },
    yAxis: {
      type: 'category',
      data: yCats,
      splitArea: { show: true },
      axisLabel: { color: textColor },
    },
    visualMap: {
      min: out.visualMin || 0,
      max: out.visualMax || 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '5%',
      textStyle: { color: textColor },
    },
    series: [
      {
        name: out.title || 'Heatmap',
        type: 'heatmap',
        data: valData,
        label: { show: true, color: textColor },
      },
    ],
  };
}
