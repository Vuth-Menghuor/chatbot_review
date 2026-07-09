import type { EChartsOption, ExtendedChartOutput, ExtendedChartSeries } from './types';

export function buildBaseOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const categories = out.data?.map((item) => String(item[out.xKey] ?? '')) || [];
  const chartType = String(out.chartType || 'bar').toLowerCase();

  const isHorizontal =
    out.horizontal === true || chartType === 'horizontal-bar' || chartType === 'horizontalbar';
  const hasDataZoom = out.dataZoom === true;

  const seriesList =
    out.series?.map((s) => {
      const seriesData =
        out.data?.map((item) => {
          const val = item[s.key];
          return typeof val === 'number' ? val : parseFloat(String(val || '0')) || 0;
        }) || [];

      const type =
        s.type || (chartType === 'area' ? 'line' : chartType === 'line' ? 'line' : 'bar');
      const isStacked = out.stacked === true || s.stack !== undefined;

      const baseSeries: Record<string, unknown> = {
        name: s.name,
        type,
        data: seriesData,
        stack: isStacked ? s.stack || 'total' : undefined,
        itemStyle: { color: s.color || '#3b82f6' },
      };

      if (type === 'line') {
        baseSeries.smooth = true;
        baseSeries.symbolSize = 6;
        baseSeries.lineStyle = { width: 3 };

        if (chartType === 'area' || s.areaStyle) {
          baseSeries.areaStyle = {
            opacity: 0.15,
            color: s.color || '#3b82f6',
          };
        }
      } else {
        baseSeries.barMaxWidth = 30;
        baseSeries.itemStyle = {
          color: s.color || '#3b82f6',
          borderRadius: isHorizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
        };
      }

      if (s.markPoint || out.markPoint) {
        baseSeries.markPoint = s.markPoint || {
          data: [
            { type: 'max', name: 'Max' },
            { type: 'min', name: 'Min' },
          ],
        };
      }
      if (s.markLine || out.markLine) {
        baseSeries.markLine = s.markLine || {
          data: [{ type: 'average', name: 'Avg' }],
        };
      }

      return baseSeries;
    }) || [];

  const categoryAxis = {
    type: 'category' as const,
    data: categories,
    axisLine: { lineStyle: { color: gridLineColor } },
    axisLabel: { color: textColor, interval: 0, rotate: categories.length > 6 ? 30 : 0 },
  };

  const valueAxis = {
    type: 'value' as const,
    axisLine: { lineStyle: { color: gridLineColor } },
    axisLabel: { color: textColor },
    splitLine: { lineStyle: { color: gridLineColor } },
  };

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
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
    grid: {
      left: '3%',
      right: '4%',
      bottom: hasDataZoom ? '20%' : '12%',
      top: '15%',
      containLabel: true,
    },
    xAxis: [isHorizontal ? valueAxis : categoryAxis],
    yAxis: [isHorizontal ? categoryAxis : valueAxis],
    dataZoom: hasDataZoom
      ? [
          {
            type: 'slider',
            show: true,
            xAxisIndex: [0],
            start: 0,
            end: 100,
            textStyle: { color: textColor },
          },
          { type: 'inside', xAxisIndex: [0], start: 0, end: 100 },
        ]
      : undefined,
    series: seriesList,
  };
}
