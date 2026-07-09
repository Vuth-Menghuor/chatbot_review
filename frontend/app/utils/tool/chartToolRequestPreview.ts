import type { ChartKind, ChartOutput } from '~/types/message';

const CHART_KIND_ALIASES: Record<string, ChartKind> = {
  line: 'line',
  bar: 'bar',
  column: 'bar',
  horizontal_bar: 'horizontal-bar',
  'horizontal-bar': 'horizontal-bar',
  horizontalbar: 'horizontalbar',
  area: 'area',
  pie: 'pie',
  doughnut: 'donut',
  donut: 'donut',
  scatter: 'scatter',
  radar: 'radar',
  heatmap: 'heatmap',
  treemap: 'treemap',
  tree_map: 'tree-map',
  'tree-map': 'tree-map',
  funnel: 'funnel',
  gauge: 'gauge',
  candlestick: 'candlestick',
  sankey: 'sankey',
  graph: 'graph',
  sunburst: 'sunburst',
};

const SERIES_COLORS = [
  '#6366f1',
  '#14b8a6',
  '#f97316',
  '#ec4899',
  '#22c55e',
  '#8b5cf6',
  '#0ea5e9',
  '#f59e0b',
];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function normalizeChartKind(value: unknown): ChartKind | undefined {
  const raw = asString(value);
  if (!raw) return undefined;
  return CHART_KIND_ALIASES[raw.toLowerCase().replace(/\s+/g, '_')];
}

function valueAt(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (record[key] !== undefined) return record[key];
  }
  return undefined;
}

function makeSeriesKey(name: string, index: number): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return base || `series_${index + 1}`;
}

function parsePoint(point: unknown): { x: string | number; y: number } | null {
  const record = asRecord(point);
  if (!record) return null;

  const x = valueAt(record, ['x', 'label', 'name', 'category']);
  const y = valueAt(record, ['y', 'value']);
  if ((typeof x !== 'string' && typeof x !== 'number') || y === undefined) return null;

  const numericY = typeof y === 'number' ? y : Number(y);
  if (!Number.isFinite(numericY)) return null;
  return { x, y: numericY };
}

function readToolParameters(input: unknown): Record<string, unknown> | null {
  const root = asRecord(input);
  if (!root) return null;

  const tool = asString(root.tool ?? root.toolName ?? root.name);
  if (tool && tool.toLowerCase() !== 'chart') return null;

  const parameters = asRecord(root.parameters) ?? asRecord(root.data) ?? root;
  return parameters;
}

export function chartToolRequestToOutput(input: unknown): ChartOutput | null {
  const parameters = readToolParameters(input);
  if (!parameters) return null;

  const seriesInput = valueAt(parameters, ['data', 'series', 'datasets']);
  if (!Array.isArray(seriesInput) || !seriesInput.length) return null;

  const rowsByX = new Map<string, Record<string, string | number>>();
  const series = seriesInput
    .map((item, index) => {
      const record = asRecord(item);
      if (!record) return null;

      const name = asString(record.name) ?? `Series ${index + 1}`;
      const key = makeSeriesKey(name, index);
      const points = valueAt(record, ['points', 'values', 'data']);
      if (!Array.isArray(points) || !points.length) return null;

      for (const rawPoint of points) {
        const point = parsePoint(rawPoint);
        if (!point) continue;
        const xKey = String(point.x);
        const row = rowsByX.get(xKey) ?? { x: point.x };
        row[key] = point.y;
        rowsByX.set(xKey, row);
      }

      return {
        key,
        name,
        color: asString(record.color) ?? SERIES_COLORS[index % SERIES_COLORS.length]!,
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item));

  const data = Array.from(rowsByX.values());
  if (!series.length || !data.length) return null;

  return {
    title: asString(parameters.title),
    chartType: normalizeChartKind(valueAt(parameters, ['chart_type', 'chartType'])) ?? 'bar',
    xKey: 'x',
    xLabel: asString(valueAt(parameters, ['x_axis_label', 'xAxisLabel', 'xLabel'])),
    yLabel: asString(valueAt(parameters, ['y_axis_label', 'yAxisLabel', 'yLabel'])),
    data,
    series,
  };
}

export function chartToolRequestToBlockContent(input: unknown): Record<string, unknown> | null {
  const output = chartToolRequestToOutput(input);
  if (!output) return null;

  return {
    toolName: 'Chart Generation',
    type: 'chart',
    mode: 'sync',
    toolStatus: 'success',
    status: 'completed',
    title: output.title,
    chartType: output.chartType,
    output,
  };
}
