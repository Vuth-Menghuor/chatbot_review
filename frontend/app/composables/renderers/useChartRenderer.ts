import { computed, type MaybeRefOrGetter, toValue } from 'vue';
import { useTheme } from 'vuetify';
import { LucideLineChart, LucideLoaderCircle, LucideTriangleAlert } from 'lucide-vue-next';
import type {
  ChartKind,
  ChartOutput,
  ChartUIToolInvocation,
  LegacyChartTask,
  MessageBlock,
} from '~/types/message';
import { buildEchartsOptionFromOutput } from '~/utils/chart';

type ChartTaskContent = LegacyChartTask & {
  state?: string;
  toolStatus?: string;
  error?: unknown;
  option?: unknown;
  echartsOption?: unknown;
};

function isChartOutputRecord(output: unknown): output is ChartOutput & Record<string, unknown> {
  return Boolean(output && typeof output === 'object' && !Array.isArray(output));
}

function isRenderableChartOutput(output: unknown): output is ChartOutput {
  if (!isChartOutputRecord(output)) return false;
  return (
    Array.isArray(output.data) ||
    Array.isArray(output.nodes) ||
    Array.isArray((output as Record<string, unknown>).links)
  );
}

function isLikelyEchartsOptionRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const o = value as Record<string, unknown>;
  return Array.isArray(o.series) || o.xAxis !== undefined;
}

function mergeChartTaskOutput(raw: ChartTaskContent): ChartOutput | undefined {
  if (!isRenderableChartOutput(raw.output)) return undefined;

  const merged = { ...raw.output };
  if (!merged.title && typeof raw.title === 'string') merged.title = raw.title;
  if (!merged.chartType && raw.chartType) merged.chartType = raw.chartType as ChartKind;
  return merged;
}

function formatPreviewValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return 'â€”';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function countDirectOptionSeries(option: unknown): number {
  if (!isLikelyEchartsOptionRecord(option)) return 0;
  const series = option.series;
  return Array.isArray(series) ? series.length : 0;
}

function adaptiveBarChartHeight(output: ChartOutput | undefined): number {
  if (!output?.data?.length || !output.series?.length) return 320;
  if (output.horizontal === true) {
    return Math.min(Math.max(300, output.data.length * 34 + 150), 620);
  }

  const chartType = String(output.chartType || 'bar').toLowerCase();
  if (chartType === 'horizontal-bar' || chartType === 'horizontalbar') {
    return Math.min(Math.max(300, output.data.length * 34 + 150), 620);
  }

  const seriesTypes = output.series.map((series) => String(series.type || chartType || 'bar').toLowerCase());
  const isBarLike = seriesTypes.every((type) => type === 'bar' || type === 'column');
  if (!isBarLike) return 320;

  const labels = output.data.map((item) => String(item[output.xKey] ?? ''));
  const averageLabelLength = labels.reduce((sum, label) => sum + label.length, 0) / Math.max(labels.length, 1);
  const maxLabelLength = Math.max(...labels.map((label) => label.length));
  const isCrowded = labels.length > 8 || averageLabelLength > 18 || maxLabelLength > 34;
  if (!isCrowded) return 320;

  const visibleRows = Math.min(labels.length, 12);
  return Math.min(Math.max(360, visibleRows * 36 + 150), 620);
}

function normalizeStatus(raw: ChartTaskContent, block: MessageBlock): string {
  const status = String(raw.status ?? raw.toolStatus ?? '').toLowerCase();
  if (status === 'success' || status === 'completed') return 'completed';
  if (status === 'error' || status === 'failed' || status === 'cancelled') return 'error';
  if (status === 'processing') return 'processing';
  if (status === 'pending') return 'pending';
  if (block.isComplete === false) return 'processing';
  return '';
}

export function useChartRenderer(blockSource: MaybeRefOrGetter<MessageBlock>) {
  const theme = useTheme();
  const isDark = computed(() => theme.global.current.value.dark);
  const block = computed(() => toValue(blockSource));
  const rawTask = computed(() => (block.value.content ?? {}) as ChartTaskContent);
  const chartOutput = computed(() => mergeChartTaskOutput(rawTask.value));
  const directOption = computed(() => rawTask.value.option ?? rawTask.value.echartsOption);
  const hasDirectOption = computed(() => isLikelyEchartsOptionRecord(directOption.value));
  const normalizedStatus = computed(() => normalizeStatus(rawTask.value, block.value));

  const invocation = computed<ChartUIToolInvocation>(() => {
    const raw = rawTask.value;

    if (typeof raw.state === 'string') {
      return {
        state: raw.state,
        output: chartOutput.value,
      };
    }

    if (normalizedStatus.value === 'error') {
      return { state: 'output-error', output: chartOutput.value };
    }

    if (normalizedStatus.value === 'pending' || normalizedStatus.value === 'processing') {
      return { state: 'input-streaming', output: undefined };
    }

    if (chartOutput.value || hasDirectOption.value) {
      return {
        state: 'output-available',
        output: chartOutput.value,
      };
    }

    if (block.value.isComplete === false) {
      return { state: 'input-streaming', output: undefined };
    }

    if (normalizedStatus.value === 'completed') {
      return { state: 'output-available', output: undefined };
    }

    return { state: 'input-available', output: undefined };
  });

  const toolName = computed(() =>
    String(rawTask.value.toolName ?? rawTask.value.title ?? '').trim(),
  );
  const taskId = computed(() => (rawTask.value.taskId ? String(rawTask.value.taskId) : undefined));
  const mode = computed(() => (rawTask.value.mode ? String(rawTask.value.mode) : undefined));
  const status = computed(() => rawTask.value.status ?? invocation.value.state);

  const color = computed(
    () =>
      ({
        'output-error': 'bg-zinc-100 text-red-600 dark:bg-red-950/25 dark:text-red-300',
      })[invocation.value.state] || 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-100',
  );

  const iconName = computed(
    () =>
      ({
        'input-available': LucideLineChart,
        'output-error': LucideTriangleAlert,
      })[invocation.value.state] || LucideLoaderCircle,
  );

  const CHART_STATUS_MESSAGES = {
    'input-available': 'Waiting for chart data...',
    'input-streaming': 'Generating chart...',
    'output-error': 'Chart could not be rendered.',
  } as const;

  const message = computed(() => {
    const s = invocation.value.state;
    if (s in CHART_STATUS_MESSAGES) {
      return CHART_STATUS_MESSAGES[s as keyof typeof CHART_STATUS_MESSAGES];
    }
    return 'Loading...';
  });

  const hasChartData = computed(() => Boolean(chartOutput.value || hasDirectOption.value));

  const echartsOption = computed(() => {
    if (isLikelyEchartsOptionRecord(directOption.value)) {
      return directOption.value;
    }

    if (chartOutput.value) {
      return buildEchartsOptionFromOutput(chartOutput.value, isDark.value);
    }

    return null;
  });

  const chartHeight = computed(() => adaptiveBarChartHeight(chartOutput.value));

  const title = computed(() => {
    const fromOutput = chartOutput.value?.title;
    if (fromOutput) return fromOutput;
    const t = rawTask.value.title;
    if (typeof t === 'string' && t.trim()) return t.trim();
    return toolName.value;
  });
  const headerIcon = computed(() => LucideLineChart);
  const isStreaming = computed(() => invocation.value.state === 'input-streaming');
  const isLoading = computed(
    () =>
      isStreaming.value ||
      normalizedStatus.value === 'pending' ||
      normalizedStatus.value === 'processing',
  );
  const isError = computed(() => invocation.value.state === 'output-error');
  const errorMessage = computed(() => {
    const err = rawTask.value.error;
    if (typeof err === 'string' && err.trim()) return err.trim();
    if (err && typeof err === 'object' && !Array.isArray(err)) {
      const msg = (err as Record<string, unknown>).message;
      if (typeof msg === 'string' && msg.trim()) return msg.trim();
    }
    return 'Chart could not be rendered.';
  });

  const previewColumns = computed(() => {
    const output = chartOutput.value;
    if (!output?.data?.length) return [];
    const seen = new Set<string>();
    const columns: Array<{ key: string; label: string }> = [];

    const addColumn = (key: string | undefined, label?: string) => {
      if (!key || seen.has(key)) return;
      seen.add(key);
      columns.push({ key, label: label || key });
    };

    addColumn(output.xKey, output.xLabel || output.xKey);
    for (const series of output.series ?? []) {
      addColumn(series.key, series.name || series.key);
      if (columns.length >= 4) break;
    }

    if (!columns.length) {
      for (const key of Object.keys(output.data[0] ?? {}).slice(0, 4)) {
        addColumn(key);
      }
    }

    return columns;
  });

  const previewRows = computed(() => {
    const output = chartOutput.value;
    if (!output?.data?.length || !previewColumns.value.length) return [];
    return output.data.slice(0, 5).map((row, index) => ({
      id: `${index}-${formatPreviewValue(row[output.xKey])}`,
      cells: previewColumns.value.map((column) => formatPreviewValue(row[column.key])),
    }));
  });

  const previewStats = computed(() => {
    const output = chartOutput.value;
    if (output?.data?.length) {
      return [
        { labelKey: 'chart.preview.rows', value: output.data.length },
        { labelKey: 'chart.preview.series', value: output.series?.length ?? 0 },
      ];
    }

    const seriesCount = countDirectOptionSeries(directOption.value);
    return seriesCount ? [{ labelKey: 'chart.preview.series', value: seriesCount }] : [];
  });

  return {
    invocation,
    color,
    iconName,
    message,
    title,
    headerIcon,
    toolName,
    taskId,
    mode,
    status,
    hasChartData,
    echartsOption,
    chartHeight,
    isStreaming,
    isLoading,
    isError,
    errorMessage,
    chartOutput,
    previewColumns,
    previewRows,
    previewStats,
  };
}
