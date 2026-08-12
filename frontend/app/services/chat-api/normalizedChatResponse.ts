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
  NormalizedOfficialReferenceBlock,
  NormalizedPredictionBlock,
  NormalizedSuggestionsBlock,
  NormalizedTableBlock,
} from '~/types/message';
import {
  isUnreliableServiceFallbackText,
  normalizeAssistantContentForUi,
  UNRELIABLE_SERVICE_FALLBACK_MESSAGE,
} from '~/utils/chat';
import { blocksToMarkerText } from '~/utils/message';
import { filterVisibleTableColumns, stripHiddenTableValues } from '~/utils/table';
import {
  parseNormalizedChatResponse,
  type ValidatedNormalizedChatResponse,
} from './normalizedChatResponseSchema';

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
  const text = normalizeAssistantContentForUi(
    firstString(obj, 'answer', 'final_answer', 'message', 'content', 'summary'),
  );
  const errors = normalizeLegacyErrors(obj.errors ?? obj.error);

  if (!text && !errors.length) return null;

  const blocks: MessageBlock[] = [];
  if (text) {
    blocks.push(
      isUnreliableServiceFallbackText(text)
        ? unreliableServiceFallbackErrorBlock(`${fallbackId}-legacy-unreliable-fallback`)
        : {
            id: `${fallbackId}-legacy-markdown`,
            type: 'markdown',
            content: text,
            isComplete: true,
          },
    );
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
    status: String(obj.status ?? '').toLowerCase() === 'failed' || errors.length || blocks.some(isUnreliableFallbackErrorBlock)
      ? 'failed'
      : 'completed',
    coverage: normalizeCoverage(obj.coverage ?? obj.answer_coverage ?? obj.status),
    confidence: normalizeConfidence(obj.confidence ?? obj.candidate_confidence),
  };
}

export function isNormalizedChatResponse(value: unknown): value is NormalizedChatResponse {
  return parseNormalizedChatResponse(value) !== null;
}

export function normalizedChatResponseToMessageParts(
  response: NormalizedChatResponse | ValidatedNormalizedChatResponse,
  fallbackId: string,
): NormalizedChatMessageParts {
  const parsed = parseNormalizedChatResponse(response);
  return parsed
    ? validatedNormalizedChatResponseToMessageParts(parsed, fallbackId)
    : invalidNormalizedResponseToMessageParts(fallbackId);
}

export function handleNormalizedChatResponse(
  response: unknown,
  fallbackId: string,
): NormalizedChatMessageParts | null {
  const parsed = parseNormalizedChatResponse(response);
  if (parsed) {
    return validatedNormalizedChatResponseToMessageParts(parsed, fallbackId);
  }
  if (isNormalizedContractEnvelope(response)) {
    if (import.meta.dev) {
      console.warn('Invalid normalized chat response', response);
    }
    return invalidNormalizedResponseToMessageParts(fallbackId);
  }
  return null;
}

function validatedNormalizedChatResponseToMessageParts(
  response: ValidatedNormalizedChatResponse,
  fallbackId: string,
): NormalizedChatMessageParts {
  const normalizedBlocks = normalizedMessageBlocks(response) ?? [];
  const blocks = normalizedBlocks.length
    ? normalizedBlocks.map((block, index) =>
        normalizedBlockToMessageBlock(block, `${response.request_id || fallbackId}-${index}`),
      )
    : fallbackResponseContentBlocks(response, fallbackId);
  const hasUnreliableFallback = blocks.some(isUnreliableFallbackErrorBlock);
  // Visual rendering uses `blocks`; keep `response.content` as the canonical
  // copy/export/accessibility fallback when the backend provides it.
  const content =
    (hasUnreliableFallback ? '' : response.response?.content) ||
    blocksToMarkerText(blocks) ||
    markdownTextFromBlocks(normalizedBlocks);

  return {
    content,
    blocks,
    sources: normalizedCitationsToSources(response.citations),
    status: hasUnreliableFallback ? 'failed' : response.status,
    coverage: response.coverage ?? response.response?.coverage,
    confidence: response.confidence ?? response.response?.confidence,
    latencyMs: numberValue(response.metrics?.latency_ms),
  };
}

function fallbackResponseContentBlocks(
  response: ValidatedNormalizedChatResponse,
  fallbackId: string,
): MessageBlock[] {
  const text = response.response?.content;
  if (!text) return [];
  if (isUnreliableServiceFallbackText(text)) {
    return [unreliableServiceFallbackErrorBlock(`${response.request_id || fallbackId}-response-unreliable-fallback`)];
  }
  return [{
    id: `${response.request_id || fallbackId}-response-fallback`,
    type: 'markdown',
    content: text,
    isComplete: true,
  }];
}

function isNormalizedContractEnvelope(value: unknown): boolean {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value) && 'api_version' in value);
}

function invalidNormalizedResponseToMessageParts(fallbackId: string): NormalizedChatMessageParts {
  const blocks: MessageBlock[] = [{
    id: `${fallbackId}-invalid-normalized-response`,
    type: 'error',
    content: {
      title: 'Response unavailable',
      message: 'The response format was not supported.',
    },
    isComplete: true,
  }];

  return {
    content: blocksToMarkerText(blocks),
    blocks,
    sources: [],
    status: 'failed',
  };
}

type SafeNormalizedChatContentBlock = ValidatedNormalizedChatResponse['message']['content'][number];

function normalizedBlockToMessageBlock(
  block: unknown | SafeNormalizedChatContentBlock,
  id: string,
): MessageBlock {
  if (!isRecord(block) || typeof block.type !== 'string') return fallbackBlockToMessageBlock(block, id);
  if (block.type === 'markdown') return markdownBlockToMessageBlock(block, id);
  if (block.type === 'summary') return passthroughBlockToMessageBlock(block, id);
  if (block.type === 'key_value') return passthroughBlockToMessageBlock(block, id);
  if (block.type === 'table') return tableBlockToMessageBlock(block, id);
  if (block.type === 'details') return passthroughBlockToMessageBlock(block, id);
  if (block.type === 'references') return passthroughBlockToMessageBlock(block, id);
  if (block.type === 'official_reference') return officialReferenceBlockToMessageBlock(block, id);
  if (block.type === 'clarification') return clarificationBlockToMessageBlock(block, id);
  if (block.type === 'error') return errorBlockToMessageBlock(block, id);
  if (block.type === 'chart') return chartBlockToMessageBlock(block, id);
  if (block.type === 'prediction') return predictionBlockToMessageBlock(block, id);
  if (block.type === 'suggestions') return suggestionsBlockToMessageBlock(block, id);
  if (block.type === 'coverage') return coverageBlockToMessageBlock(block, id);
  return {
    id,
    type: 'fallback',
    content: 'Unsupported response content',
    isComplete: true,
  };
}

function passthroughBlockToMessageBlock(block: NormalizedChatContentBlock, id: string): MessageBlock {
  return {
    id,
    type: block.type,
    title: 'title' in block ? block.title : undefined,
    content: block,
    isComplete: true,
  };
}

function markdownBlockToMessageBlock(block: NormalizedMarkdownBlock, id: string): MessageBlock {
  const content = normalizeAssistantContentForUi(typeof block.text === 'string' ? block.text : '');
  if (isUnreliableServiceFallbackText(content)) {
    return unreliableServiceFallbackErrorBlock(`${id}-unreliable-fallback`);
  }

  return {
    id,
    type: 'markdown',
    content,
    isComplete: true,
  };
}

function unreliableServiceFallbackErrorBlock(id: string): MessageBlock {
  return {
    id,
    type: 'error',
    content: {
      title: 'Response unavailable',
      message: UNRELIABLE_SERVICE_FALLBACK_MESSAGE,
    },
    isComplete: true,
  };
}

function isUnreliableFallbackErrorBlock(block: MessageBlock): boolean {
  return block.type === 'error' &&
    typeof block.content === 'object' &&
    block.content !== null &&
    'message' in block.content &&
    block.content.message === UNRELIABLE_SERVICE_FALLBACK_MESSAGE;
}

function tableBlockToMessageBlock(block: NormalizedTableBlock, id: string): MessageBlock {
  const rawColumns = Array.isArray(block.columns) ? block.columns : [];
  const columns = filterVisibleTableColumns(rawColumns);
  const rows = Array.isArray(block.rows)
    ? block.rows.map((row) => stripHiddenTableValues(row, rawColumns))
    : [];
  return {
    id,
    type: 'table',
    title: block.title,
    content: {
      columns: columns.map((column) => ({ key: column.key, title: column.label })),
      rows,
    },
    isComplete: true,
  };
}

function officialReferenceBlockToMessageBlock(block: NormalizedOfficialReferenceBlock, id: string): MessageBlock {
  return {
    id,
    type: 'official_reference',
    title: block.title,
    content: {
      title: block.title,
      label: block.label,
      url: block.url,
      agency: block.agency,
      sourceType: block.source_type,
    },
    isComplete: true,
  };
}

function clarificationBlockToMessageBlock(
  block: NormalizedClarificationBlock,
  id: string,
): MessageBlock {
  const title = block.title || 'More information is needed';
  const questionItems = Array.isArray(block.questions) ? block.questions : [];
  return {
    id,
    type: 'clarification',
    title,
    content: {
      kind: 'form',
      title,
      fields: questionItems.map((question, index) => ({
        name: `clarification_${index + 1}`,
        label: question,
        type: 'text',
        required: true,
      })),
      actions: [{ id: 'submit', label: 'Submit', primary: true }],
    },
    isComplete: true,
  };
}

function errorBlockToMessageBlock(block: NormalizedErrorBlock, id: string): MessageBlock {
  return {
    id,
    type: 'error',
    content: {
      title: 'Request failed',
      message: typeof block.message === 'string' ? block.message : 'Request failed',
    },
    isComplete: true,
  };
}

function chartBlockToMessageBlock(block: NormalizedChartBlock, id: string): MessageBlock {
  const data = block.data && typeof block.data === 'object' && !Array.isArray(block.data) ? block.data : {};
  return {
    id,
    type: 'chart',
    title: block.title,
    content: {
      ...data,
      title: block.title ?? data.title,
      chartType: data.chartType,
      status: 'completed',
      state: 'output-available',
      output: data,
    },
    isComplete: true,
  };
}

function predictionBlockToMessageBlock(block: NormalizedPredictionBlock, id: string): MessageBlock {
  const data = block.data && typeof block.data === 'object' && !Array.isArray(block.data) ? block.data : {};
  const displayData = withoutPredictionConfidence(data);
  return {
    id,
    type: 'prediction',
    title: block.title,
    content: {
      ...displayData,
      title: block.title,
      hsCode: stringValue(data.hsCode),
      productName: stringValue(data.description),
    },
    isComplete: true,
  };
}

function withoutPredictionConfidence(data: Record<string, unknown>): Record<string, unknown> {
  const {
    confidence: _confidence,
    confidenceLabel: _confidenceLabel,
    candidate_confidence: _candidateConfidence,
    alternatives,
    ...displayData
  } = data;

  if (Array.isArray(alternatives)) {
    displayData.alternatives = alternatives.map((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return item;
      const {
        confidence: _altConfidence,
        confidenceLabel: _altConfidenceLabel,
        candidate_confidence: _altCandidateConfidence,
        ...displayItem
      } = item as Record<string, unknown>;
      return displayItem;
    });
  }

  return displayData;
}

function suggestionsBlockToMessageBlock(block: NormalizedSuggestionsBlock, id: string): MessageBlock {
  return {
    id,
    type: 'suggestions',
    title: block.title,
    content: Array.isArray(block.items) ? block.items : [],
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
      items: Array.isArray(block.items) ? block.items : [],
      note: block.note,
    },
    isComplete: true,
  };
}

function normalizedCitationsToSources(citations: NormalizedChatResponse['citations']): MessageSource[] {
  return (citations ?? []).map((citation, index) => ({
    marker: citation.marker,
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

function markdownTextFromBlocks(blocks: unknown[]): string {
  return blocks
    .map((block) => {
      if (!isRecord(block) || typeof block.type !== 'string') return '';
      if (block.type === 'markdown') return block.text;
      if (block.type === 'error') return block.message;
      if (block.type === 'clarification' && Array.isArray(block.questions)) return block.questions.join('\n');
      return '';
    })
    .filter(Boolean)
    .join('\n\n');
}

function normalizedMessageBlocks(response: { message?: { content?: unknown; blocks?: unknown } | null }): unknown[] | null {
  const message = response.message;
  if (!message || typeof message !== 'object' || Array.isArray(message)) return null;
  const value = Array.isArray(message.content) ? message.content : message.blocks;
  return Array.isArray(value) ? value : null;
}

function fallbackBlockToMessageBlock(block: unknown, id: string): MessageBlock {
  return {
    id,
    type: 'fallback',
    content: stringifyFallbackBlock(block),
    isComplete: true,
  };
}

function stringifyFallbackBlock(block: unknown): string {
  if (typeof block === 'string') return block;
  try {
    return JSON.stringify(block, null, 2);
  } catch {
    return String(block);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
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
