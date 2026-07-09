import type { EChartsOption, ExtendedChartOutput } from './types';
import { buildGaugeOption } from './gauge';
import { buildFunnelOption } from './funnel';
import { buildTreemapOption } from './treemap';
import { buildRadarOption } from './radar';
import { buildPieOption } from './pie';
import { buildSankeyOption } from './sankey';
import { buildGraphOption } from './graph';
import { buildSunburstOption } from './sunburst';
import { buildCandlestickOption } from './candlestick';
import { buildHeatmapOption } from './heatmap';
import { buildScatterOption } from './scatter';
import { buildBaseOption } from './base';

export { echarts, ensureEChartsRegistered } from './echartsRegister';

export function buildEchartsOptionFromOutput(
  out: ExtendedChartOutput,
  isDark: boolean,
): EChartsOption {
  const chartType = String(out.chartType || 'bar').toLowerCase();

  switch (chartType) {
    case 'gauge':
      return buildGaugeOption(out, isDark);
    case 'funnel':
      return buildFunnelOption(out, isDark);
    case 'treemap':
    case 'tree-map':
      return buildTreemapOption(out, isDark);
    case 'radar':
      return buildRadarOption(out, isDark);
    case 'pie':
    case 'donut':
      return buildPieOption(out, isDark);
    case 'sankey':
      return buildSankeyOption(out, isDark);
    case 'graph':
      return buildGraphOption(out, isDark);
    case 'sunburst':
      return buildSunburstOption(out, isDark);
    case 'candlestick':
      return buildCandlestickOption(out, isDark);
    case 'heatmap':
      return buildHeatmapOption(out, isDark);
    case 'scatter':
      return buildScatterOption(out, isDark);
    default:
      return buildBaseOption(out, isDark);
  }
}
