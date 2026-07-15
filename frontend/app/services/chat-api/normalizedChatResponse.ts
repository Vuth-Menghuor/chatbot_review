import type {
  MessageBlock,
  MessageSource,
  MessageStatus,
  NormalizedChartBlock,
  NormalizedChatContentBlock,
  NormalizedChatResponse,
  NormalizedClarificationBlock,
  NormalizedErrorBlock,
  NormalizedMarkdownBlock,
  NormalizedTableBlock,
} from '~/types/message';
import { blocksToMarkerText } from '~/utils/message';

export interface NormalizedChatMessageParts {
  content: string;
  blocks: MessageBlock[];
  sources: MessageSource[];
  status: MessageStatus;
}

export function legacyChatResponseToMessageParts(
  value: unknown,
  fallbackId: string,
): NormalizedChatMessageParts | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const obj = value as Record<string, unknown>;
  const text = firstString(obj, 'answer', 'final_answer', 'message', 'content', 'summary');
  const errors = normalizeLegacyErrors(obj.errors ?? obj.error);

  if (!text && !errors.length) return null;

  const blocks: MessageBlock[] = [];
  if (text) {
    blocks.push({
      id: `${fallbackId}-legacy-markdown`,
      type: 'markdown',
      content: text,
      isComplete: true,
    });
  }
  errors.forEach((message, index) => {
    blocks.push({
      id: `${fallbackId}-legacy-error-${index}`,
      type: 'error',
      content: {
        title: 'Request failed',
        message,
      },
      isComplete: true,
    });
  });

  return {
    content: blocksToMarkerText(blocks) || text || errors.join('\n'),
    blocks,
    sources: normalizedCitationsToSources(normalizeLegacyCitations(obj.citations ?? obj.references)),
    status: String(obj.status ?? '').toLowerCase() === 'failed' || errors.length ? 'failed' : 'completed',
  };
}

export function isNormalizedChatResponse(value: unknown): value is NormalizedChatResponse {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const obj = value as Partial<NormalizedChatResponse>;
  return (
    typeof obj.request_id === 'string' &&
    typeof obj.session_id === 'string' &&
    typeof obj.intent === 'string' &&
    Boolean(obj.message) &&
    Array.isArray(obj.message?.content)
  );
}

export function normalizedChatResponseToMessageParts(
  response: NormalizedChatResponse,
  fallbackId: string,
): NormalizedChatMessageParts {
  const blocks = response.message.content.map((block, index) =>
    normalizedBlockToMessageBlock(block, `${response.request_id || fallbackId}-${index}`),
  );
  if (response.suggestions?.length) {
    blocks.push({
      id: `${response.request_id || fallbackId}-suggestions`,
      type: 'suggestions',
      content: response.suggestions,
      isComplete: true,
    });
  }
  const content = blocksToMarkerText(blocks) || markdownTextFromBlocks(response.message.content);

  return {
    content,
    blocks,
    sources: normalizedCitationsToSources(response.citations),
    status: response.status === 'failed' ? 'failed' : 'completed',
  };
}

function normalizedBlockToMessageBlock(
  block: NormalizedChatContentBlock,
  id: string,
): MessageBlock {
  if (block.type === 'markdown') return markdownBlockToMessageBlock(block, id);
  if (block.type === 'table') return tableBlockToMessageBlock(block, id);
  if (block.type === 'clarification') return clarificationBlockToMessageBlock(block, id);
  if (block.type === 'error') return errorBlockToMessageBlock(block, id);
  if (block.type === 'chart') return chartBlockToMessageBlock(block, id);
  return {
    id,
    type: 'fallback',
    content: JSON.stringify(block, null, 2),
    isComplete: true,
  };
}

function markdownBlockToMessageBlock(block: NormalizedMarkdownBlock, id: string): MessageBlock {
  return {
    id,
    type: 'markdown',
    content: block.text,
    isComplete: true,
  };
}

function tableBlockToMessageBlock(block: NormalizedTableBlock, id: string): MessageBlock {
  return {
    id,
    type: 'table',
    title: block.title,
    content: {
      columns: block.columns.map((column) => ({ key: column.key, title: column.label })),
      rows: block.rows,
    },
    isComplete: true,
  };
}

function clarificationBlockToMessageBlock(
  block: NormalizedClarificationBlock,
  id: string,
): MessageBlock {
  const title = block.title || 'More information is needed';
  const questions = block.questions.map((question) => `- ${question}`).join('\n');
  return {
    id,
    type: 'markdown',
    title,
    content: `**${title}**\n\n${questions}`,
    isComplete: true,
  };
}

function errorBlockToMessageBlock(block: NormalizedErrorBlock, id: string): MessageBlock {
  return {
    id,
    type: 'error',
    content: {
      title: 'Request failed',
      message: block.message,
    },
    isComplete: true,
  };
}

function chartBlockToMessageBlock(block: NormalizedChartBlock, id: string): MessageBlock {
  const output = normalizedChartDataToOutput(block);
  return {
    id,
    type: 'chart',
    title: block.title,
    content: {
      ...block.data,
      title: block.title ?? block.data.title,
      status: 'completed',
      state: 'output-available',
      output,
    },
    isComplete: true,
  };
}

function normalizedChartDataToOutput(block: NormalizedChartBlock): Record<string, unknown> {
  const data = block.data;
  const title = block.title ?? data.title;
  const chartType = normalizeChartType(data.type ?? data.chartType);

  if (Array.isArray(data.labels) && Array.isArray(data.datasets)) {
    const labels = data.labels.map((label) => String(label));
    const datasets = data.datasets.filter(isRecord);
    const renderType = chartType === 'line' && labels.length < 2 ? 'bar' : chartType;
    const rows = labels.map((label, index) => {
      const row: Record<string, string | number> = { label };
      datasets.forEach((dataset, datasetIndex) => {
        const key = chartSeriesKey(dataset, datasetIndex);
        const values = Array.isArray(dataset.data) ? dataset.data : [];
        row[key] = numericCell(values[index]);
      });
      return row;
    });

    return {
      title,
      chartType: renderType,
      xKey: 'label',
      xLabel: 'Label',
      yLabel: datasets[0]?.label ? String(datasets[0].label) : undefined,
      data: rows,
      series: datasets.map((dataset, index) => ({
        key: chartSeriesKey(dataset, index),
        name: String(dataset.label ?? `Series ${index + 1}`),
        color: chartColor(index),
        type: renderType === 'line' ? 'line' : 'bar',
      })),
    };
  }

  return {
    ...data,
    title,
    chartType,
  };
}

function normalizeChartType(value: unknown): string {
  const raw = String(value || 'bar').toLowerCase();
  if (raw === 'horizontalbar') return 'horizontal-bar';
  if (raw === 'doughnut') return 'donut';
  return raw;
}

function chartSeriesKey(dataset: Record<string, unknown>, index: number): string {
  const label = String(dataset.label ?? `series_${index + 1}`)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return label || `series_${index + 1}`;
}

function numericCell(value: unknown): number {
  if (typeof value === 'number') return value;
  const parsed = parseFloat(String(value ?? '0'));
  return Number.isFinite(parsed) ? parsed : 0;
}

function chartColor(index: number): string {
  return ['#2563eb', '#16a34a', '#dc2626', '#9333ea', '#ea580c', '#0891b2'][index % 6];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function normalizedCitationsToSources(citations: NormalizedChatResponse['citations']): MessageSource[] {
  return (citations ?? []).map((citation, index) => ({
    title: citation.title || citation.label || `Source ${index + 1}`,
    url: citation.url,
    snippet: citation.snippet,
    domain: citation.url ? safeDomain(citation.url) : undefined,
  }));
}

function markdownTextFromBlocks(blocks: NormalizedChatContentBlock[]): string {
  return blocks
    .map((block) => {
      if (block.type === 'markdown') return block.text;
      if (block.type === 'error') return block.message;
      if (block.type === 'clarification') return block.questions.join('\n');
      return '';
    })
    .filter(Boolean)
    .join('\n\n');
}

function safeDomain(url: string): string | undefined {
  try {
    return new URL(url).hostname;
  } catch {
    return undefined;
  }
}

function firstString(obj: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
}

function normalizeLegacyErrors(value: unknown): string[] {
  if (!value) return [];
  if (typeof value === 'string') return value.trim() ? [value] : [];
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const obj = item as Record<string, unknown>;
          return firstString(obj, 'message', 'detail', 'code');
        }
        return '';
      })
      .filter(Boolean);
  }
  if (typeof value === 'object') {
    const text = firstString(value as Record<string, unknown>, 'message', 'detail', 'code');
    return text ? [text] : [];
  }
  return [];
}

function normalizeLegacyCitations(value: unknown): NormalizedChatResponse['citations'] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item, index) => {
      if (typeof item === 'string') {
        return {
          id: String(index + 1),
          title: item,
          label: `Source ${index + 1}`,
        };
      }
      if (!item || typeof item !== 'object') return null;
      const obj = item as Record<string, unknown>;
      return {
        id: String(obj.id ?? obj.doc_id ?? obj.source_id ?? obj.reference_id ?? index + 1),
        label: String(obj.label ?? `Source ${index + 1}`),
        title: typeof obj.title === 'string' ? obj.title : typeof obj.source === 'string' ? obj.source : undefined,
        snippet: typeof obj.snippet === 'string' ? obj.snippet : typeof obj.content === 'string' ? obj.content : undefined,
        url: typeof obj.url === 'string' ? obj.url : typeof obj.source_url === 'string' ? obj.source_url : undefined,
        score: typeof obj.score === 'number' ? obj.score : undefined,
      };
    })
    .filter((citation): citation is NormalizedChatResponse['citations'][number] => Boolean(citation));
}
