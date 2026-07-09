/**
 * Frontend-only "async chart" simulation: sync chart tools from the API are
 * normalized into `mode: "async"` with a deterministic `local-chart:` taskId.
 *
 * These `local-chart:*` ids are **not** backend task identifiers: the UI must never
 * send them to HTTP poll endpoints or to the chat server. They exist only so the same
 * merge pipeline as real async charts can show a processing row first, then apply the
 * full chart payload from an in-memory map on the next animation frame
 * (see `scheduleDeferredLocalChartTaskMerges` in `useAsyncToolTaskPoll.ts`).
 */

import type { ChartKind, ChartOutput } from '~/types/message';
import type { ChartToolData, UnifiedAsyncTool, UnifiedToolItem } from '~/types/unified';

export const LOCAL_CHART_TASK_PREFIX = 'local-chart:';

const resolutions = new Map<string, UnifiedToolItem>();

export function isLocalChartTaskId(taskId: string | undefined): boolean {
  return typeof taskId === 'string' && taskId.startsWith(LOCAL_CHART_TASK_PREFIX);
}

export function makeLocalChartTaskId(requestId: string | undefined, toolIndex: number): string {
  const rid = typeof requestId === 'string' && requestId.trim() ? requestId.trim() : 'req';
  return `${LOCAL_CHART_TASK_PREFIX}${rid}-${toolIndex}`;
}

function isChartOutputLike(value: unknown): value is ChartOutput {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const o = value as Record<string, unknown>;
  if (typeof o.xKey === 'string' && Array.isArray(o.data) && o.data.length > 0) return true;
  return Array.isArray(o.nodes) || Array.isArray(o.links);
}

function isLikelyEchartsOption(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const o = value as Record<string, unknown>;
  return Array.isArray(o.series) || o.xAxis !== undefined;
}

function flattenToolData(data: unknown): Record<string, unknown> | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const root = data as Record<string, unknown>;
  const inner = root.content;
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
    return { ...root, ...(inner as Record<string, unknown>) };
  }
  return root;
}

function coerceChartKind(value: unknown): ChartKind | undefined {
  if (typeof value !== 'string') return undefined;
  const v = value.trim().toLowerCase();
  const supported = new Set<string>([
    'line',
    'bar',
    'horizontal-bar',
    'horizontalbar',
    'area',
    'pie',
    'donut',
    'scatter',
    'radar',
    'heatmap',
    'treemap',
    'tree-map',
    'funnel',
    'gauge',
    'candlestick',
    'sankey',
    'graph',
    'sunburst',
  ]);
  if (supported.has(v)) return v as ChartKind;
  return undefined;
}

/**
 * If `data` carries a renderable chart payload (`ChartOutput`, ECharts `option`, or `echartsOption`
 * including values nested under `content`), returns slim vs full shapes for the pending vs resolved tool rows.
 */
export function extractRenderableChartToolData(data: unknown): {
  slim: Pick<ChartToolData, 'title' | 'chartType'>;
  full: ChartToolData;
} | null {
  const flat = flattenToolData(data);
  if (!flat) return null;

  const title = typeof flat.title === 'string' ? flat.title : undefined;
  const chartType = coerceChartKind(flat.chartType);

  const output = flat.output;
  if (isChartOutputLike(output)) {
    const full: ChartToolData = {
      title: output.title ?? title,
      chartType: output.chartType ?? chartType,
      output,
    };
    return {
      slim: { title: full.title, chartType: full.chartType },
      full,
    };
  }

  const option = flat.option;
  if (isLikelyEchartsOption(option)) {
    const full: ChartToolData = {
      title,
      chartType,
      option,
    };
    return { slim: { title, chartType }, full };
  }

  const echartsOption = flat.echartsOption;
  if (isLikelyEchartsOption(echartsOption)) {
    const full: ChartToolData = {
      title,
      chartType,
      echartsOption,
    };
    return { slim: { title, chartType }, full };
  }

  return null;
}

function isChartUnifiedTool(tool: UnifiedToolItem): boolean {
  const t = String(tool.type || '')
    .toLowerCase()
    .trim();
  return t === 'chart' || t === 'graph';
}

export function registerLocalChartTaskResolution(
  taskId: string,
  resolvedTool: UnifiedToolItem,
): void {
  if (!isLocalChartTaskId(taskId)) return;
  if (!resolutions.has(taskId)) resolutions.set(taskId, resolvedTool);
}

/** Removes and returns the registered resolution (one-shot merge). */
export function takeLocalChartTaskResolution(taskId: string): UnifiedToolItem | undefined {
  const row = resolutions.get(taskId);
  if (row) resolutions.delete(taskId);
  return row;
}

/**
 * Converts a successful sync chart tool row into a frontend-only deferred chart render:
 * the visible tool row uses `mode: "async"`, `status: "processing"`, and a `local-chart:`
 * `taskId` (never a server task); the resolved success payload is registered for a
 * one-shot rAF merge into the same assistant message.
 */
export function prepareSyncChartToolForDeferredRender(
  tool: UnifiedToolItem,
  requestId: string | undefined,
  toolIndex: number,
): UnifiedToolItem {
  const config = useRuntimeConfig();
  const publicConfig = config.public as Record<string, unknown>;
  const enabled =
    publicConfig.localChartDeferEnabled === true ||
    publicConfig.localChartDeferEnabled === 'true';
  if (!enabled) return tool;
  if (!isChartUnifiedTool(tool)) return tool;
  if (tool.mode !== 'sync' || tool.status !== 'success') return tool;

  const extracted = extractRenderableChartToolData(tool.data);
  if (!extracted) return tool;

  const taskId = makeLocalChartTaskId(requestId, toolIndex);
  const resolved: UnifiedAsyncTool = {
    ...tool,
    mode: 'async',
    status: 'success',
    taskId,
    data: extracted.full,
  };

  registerLocalChartTaskResolution(taskId, resolved);

  return {
    ...tool,
    mode: 'async',
    status: 'processing',
    taskId,
    data: extracted.slim,
  } as UnifiedToolItem;
}
