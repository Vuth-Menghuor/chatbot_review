import type { EChartsOption, ExtendedChartOutput, ExtendedChartSeries } from './types';
import { chartColor, chartPalette, seriesColor } from './palette';

const ADAPTIVE_BAR_LIMIT = 12;
const CROWDED_CATEGORY_COUNT = 8;
const LONG_LABEL_LENGTH = 18;
const MAX_AXIS_LABEL_LENGTH = 34;

export function buildBaseOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  const chartType = String(out.chartType || 'bar').toLowerCase();
  const sourceData = out.data || [];
  const shouldAdapt = shouldUseAdaptiveHorizontalBar(out, chartType);
  const displayData = shouldAdapt ? topRowsForBarDisplay(out, ADAPTIVE_BAR_LIMIT) : sourceData;
  const categories = displayData.map((item) => String(item[out.xKey] ?? ''));

  const isHorizontal =
    shouldAdapt ||
    out.horizontal === true ||
    chartType === 'horizontal-bar' ||
    chartType === 'horizontalbar';
  const hasDataZoom = out.dataZoom === true && !shouldAdapt;

  const seriesList =
    out.series?.map((s, seriesIndex) => {
      const seriesData =
        displayData.map((item, dataIndex) => {
          const val = item[s.key];
          const value = typeof val === 'number' ? val : parseFloat(String(val || '0')) || 0;
          if (out.series?.length === 1 && isBarLikeChartType(chartType, s.type)) {
            return {
              value,
              itemStyle: { color: chartColor(dataIndex, isDark) },
            };
          }
          return value;
        });
      const color = seriesColor(s.color, seriesIndex, isDark);

      const type =
        s.type || (chartType === 'area' ? 'line' : chartType === 'line' ? 'line' : 'bar');
      const isStacked = out.stacked === true || s.stack !== undefined;

      const baseSeries: Record<string, unknown> = {
        name: s.name,
        type,
        data: seriesData,
        stack: isStacked ? s.stack || 'total' : undefined,
        itemStyle: { color },
      };

      if (type === 'line') {
        baseSeries.smooth = true;
        baseSeries.symbolSize = 6;
        baseSeries.lineStyle = { width: 3 };

        if (chartType === 'area' || s.areaStyle) {
          baseSeries.areaStyle = {
            opacity: 0.15,
            color,
          };
        }
      } else {
        baseSeries.barMaxWidth = 30;
        baseSeries.itemStyle = {
          color,
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
    axisLabel: {
      color: textColor,
      interval: 0,
      rotate: isHorizontal ? 0 : categories.length > 6 ? 30 : 0,
      formatter: (value: string) => truncateAxisLabel(value, isHorizontal ? 46 : MAX_AXIS_LABEL_LENGTH),
    },
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
      subtext:
        shouldAdapt && sourceData.length > displayData.length
          ? `Showing top ${displayData.length} of ${sourceData.length}`
          : undefined,
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
      subtextStyle: { color: isDark ? '#a1a1aa' : '#71717a', fontSize: 12 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      borderWidth: 1,
      textStyle: { color: textColor },
    },
    color: chartPalette(isDark),
    legend: {
      orient: 'horizontal',
      bottom: '0%',
      left: 'center',
      textStyle: { color: textColor },
    },
    grid: {
      left: isHorizontal ? '4%' : '3%',
      right: '4%',
      bottom: hasDataZoom ? '20%' : '12%',
      top: shouldAdapt ? '18%' : '15%',
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

function isBarLikeChartType(chartType: string, seriesType: unknown): boolean {
  const type = String(seriesType || chartType || 'bar').toLowerCase();
  return type === 'bar' || type === 'column' || type === 'horizontal-bar' || type === 'horizontalbar';
}

function shouldUseAdaptiveHorizontalBar(out: ExtendedChartOutput, chartType: string): boolean {
  if (out.horizontal === true || chartType === 'horizontal-bar' || chartType === 'horizontalbar') {
    return false;
  }

  const data = out.data || [];
  if (!data.length || !out.series?.length || !out.xKey) return false;

  const seriesTypes = out.series.map((series) => String(series.type || chartType || 'bar').toLowerCase());
  const isBarLike = seriesTypes.every((type) => type === 'bar' || type === 'column');
  if (!isBarLike) return false;

  const labels = data.map((item) => String(item[out.xKey] ?? ''));
  const averageLabelLength = labels.reduce((sum, label) => sum + label.length, 0) / Math.max(labels.length, 1);
  const maxLabelLength = Math.max(...labels.map((label) => label.length));

  return (
    labels.length > CROWDED_CATEGORY_COUNT ||
    averageLabelLength > LONG_LABEL_LENGTH ||
    maxLabelLength > MAX_AXIS_LABEL_LENGTH
  );
}

function topRowsForBarDisplay(out: ExtendedChartOutput, limit: number) {
  const data = out.data || [];
  if (data.length <= limit) return data;

  const seriesKeys = out.series?.map((series) => series.key).filter(Boolean) || [];
  if (!seriesKeys.length) return data.slice(0, limit);

  return [...data]
    .sort((a, b) => rowSeriesTotal(b, seriesKeys) - rowSeriesTotal(a, seriesKeys))
    .slice(0, limit);
}

function rowSeriesTotal(row: Record<string, string | number>, keys: string[]) {
  return keys.reduce((sum, key) => {
    const value = row[key];
    return sum + (typeof value === 'number' ? value : parseFloat(String(value || '0')) || 0);
  }, 0);
}

function truncateAxisLabel(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(maxLength - 1, 1))}…`;
}
