import type {
  MessageBlock,
  MessageSource,
  MessageStatus,
  AnswerConfidence,
  AnswerCoverage,
  NormalizedChartBlock,
  NormalizedChatContentBlock,
  NormalizedChatResponse,
  NormalizedClarificationBlock,
  NormalizedCoverageBlock,
  NormalizedErrorBlock,
  NormalizedMarkdownBlock,
  NormalizedSuggestionsBlock,
  NormalizedTableBlock,
} from '~/types/message';
import { blocksToMarkerText } from '~/utils/message';

export interface NormalizedChatMessageParts {
  content: string;
  blocks: MessageBlock[];
  sources: MessageSource[];
  status: MessageStatus;
  coverage?: AnswerCoverage;
  confidence?: AnswerConfidence;
  latencyMs?: number;
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
    coverage: normalizeCoverage(obj.coverage ?? obj.answer_coverage ?? obj.status),
    confidence: normalizeConfidence(obj.confidence ?? obj.candidate_confidence),
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
  const content = blocksToMarkerText(blocks) || markdownTextFromBlocks(response.message.content);

  return {
    content,
    blocks,
    sources: normalizedCitationsToSources(response.citations),
    status: response.status === 'failed' ? 'failed' : 'completed',
    coverage: response.coverage ?? response.response?.coverage,
    confidence: response.confidence ?? response.response?.confidence,
    latencyMs: numberValue(response.metrics?.latency_ms),
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
  if (block.type === 'suggestions') return suggestionsBlockToMessageBlock(block, id);
  if (block.type === 'coverage') return coverageBlockToMessageBlock(block, id);
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
  return {
    id,
    type: 'chart',
    title: block.title,
    content: {
      ...block.data,
      title: block.title ?? block.data.title,
      chartType: block.data.chartType,
      status: 'completed',
      state: 'output-available',
      output: block.data,
    },
    isComplete: true,
  };
}

function suggestionsBlockToMessageBlock(block: NormalizedSuggestionsBlock, id: string): MessageBlock {
  return {
    id,
    type: 'suggestions',
    title: block.title,
    content: block.items,
    isComplete: true,
  };
}

function coverageBlockToMessageBlock(block: NormalizedCoverageBlock, id: string): MessageBlock {
  return {
    id,
    type: 'coverage',
    title: block.title,
    content: {
      title: block.title,
      tone: block.tone ?? 'info',
      items: block.items,
      note: block.note,
    },
    isComplete: true,
  };
}

function normalizedCitationsToSources(citations: NormalizedChatResponse['citations']): MessageSource[] {
  return (citations ?? []).map((citation, index) => ({
    title: citation.title || citation.filename || citation.document_id || citation.label || `Source ${index + 1}`,
    url: citation.url,
    snippet: citation.snippet,
    domain: citation.url ? safeDomain(citation.url) : undefined,
    id: citation.id,
    citationId: citation.citation_id ?? citation.id,
    documentId: citation.document_id,
    filename: citation.filename,
    chunkIndex: citation.chunk_index,
    retrievalMethod: citation.retrieval_method,
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

function normalizeCoverage(value: unknown): AnswerCoverage | undefined {
  const coverage = String(value || '').toLowerCase();
  if (['complete', 'full', 'high'].includes(coverage)) return 'complete';
  if (['partial', 'partial_answer', 'limited', 'incomplete'].includes(coverage)) return 'partial';
  if (coverage === 'unknown') return 'unknown';
  return undefined;
}

function normalizeConfidence(value: unknown): AnswerConfidence | undefined {
  const confidence = String(value || '').toLowerCase();
  if (confidence === 'high' || confidence === 'medium' || confidence === 'low') return confidence;
  if (confidence === 'med' || confidence === 'moderate') return 'medium';
  return undefined;
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
      const metadata = obj.metadata && typeof obj.metadata === 'object' && !Array.isArray(obj.metadata)
        ? (obj.metadata as Record<string, unknown>)
        : {};
      const documentId = stringValue(obj.document_id ?? obj.documentId ?? metadata.document_id ?? metadata.doc_id);
      const filename = stringValue(obj.filename ?? metadata.filename ?? metadata.file_name);
      return {
        id: String(obj.id ?? obj.citation_id ?? obj.doc_id ?? obj.source_id ?? obj.reference_id ?? documentId ?? index + 1),
        label: String(obj.label ?? `Source ${index + 1}`),
        title: stringValue(obj.title ?? obj.source ?? metadata.title ?? metadata.source ?? filename ?? documentId),
        snippet: typeof obj.snippet === 'string' ? obj.snippet : typeof obj.content === 'string' ? obj.content : undefined,
        url: typeof obj.url === 'string' ? obj.url : typeof obj.source_url === 'string' ? obj.source_url : undefined,
        score: typeof obj.score === 'number' ? obj.score : undefined,
        citation_id: stringValue(obj.citation_id ?? obj.id),
        document_id: documentId,
        filename,
        chunk_index: numberValue(obj.chunk_index ?? obj.chunk_idx ?? metadata.chunk_index ?? metadata.chunk_idx),
        retrieval_method: stringValue(obj.retrieval_method ?? obj.retrievalMethod ?? metadata.retrieval_method),
        metadata,
      };
    })
    .filter((citation): citation is NormalizedChatResponse['citations'][number] => Boolean(citation));
}

function stringValue(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number') return String(value);
  return undefined;
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}
