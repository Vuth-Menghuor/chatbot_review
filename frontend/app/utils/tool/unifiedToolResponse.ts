/**
 * Unified Tool Response (v2 / MCP-like) adapter layer.
 *
 * Converts the standardized `UnifiedToolResponse` envelope into:
 *   - a list of canonical `MessageBlock`s for direct rendering, and
 *   - a flat list of "task states" describing async tools that the UI
 *     can subscribe to (e.g. polling/streaming a `taskId`).
 *
 * It also provides the inverse helper `unifiedResponseToMarkerText` which
 * serializes the envelope into the legacy raw-marker text format so it
 * flows through the existing streaming/parsing pipeline transparently.
 *
 * The adapter is intentionally permissive: any unknown `toolName`/`type`
 * value safely falls through to a `tool_output` block instead of throwing.
 */

import type {
  ChartToolData,
  ImageToolData,
  MessageBlock,
  MessageBlockType,
  OcrToolData,
  PredictionToolData,
  ReportToolData,
  StructuredToolData,
  UnifiedAsyncTaskState,
  UnifiedNormalizationResult,
  UnifiedAsyncTool,
  UnifiedStreamTool,
  UnifiedSyncTool,
  UnifiedToolError,
  UnifiedToolItem,
  UnifiedToolResponse,
  WorkflowStep,
  WorkflowToolData,
} from '~/types/message';
import { normalizeToolData } from '~/types/toolSchemas';
import {
  mergeToolEnvelopeIntoContent,
  toolEnvelopeContentFields,
  toolEnvelopeFromUnifiedItem,
} from './toolResponseContract';
import { serializeBlockForMarkerPipeline } from '../message/blockMarkerSerialization';
import { canonicalizeBlockType } from '../message/canonicalBlocks';
import { prepareSyncChartToolForDeferredRender } from './localAsyncChartTasks';
import { prepareSyncImageToolForDeferredRender } from './localAsyncImageTasks';
import {
  calculatorDataToMarkdown,
  mathDataToMarkdown,
} from './formulaToMarkdown';
import { uid } from '../id';

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Type guard for the v2 unified envelope. Use this to disambiguate from
 * legacy raw-marker text in dual-format entry points.
 */
export function isUnifiedToolResponse(value: unknown): value is UnifiedToolResponse {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.requestId === 'string' &&
    typeof obj.mode === 'string' &&
    typeof obj.status === 'string' &&
    Array.isArray(obj.tools)
  );
}

/**
 * Normalizes a unified envelope into canonical render blocks and async task
 * placeholders. The output preserves tool order so multi-tool responses
 * display in the order the backend produced them.
 */
export function normalizeUnifiedToolResponse(
  envelope: UnifiedToolResponse,
): UnifiedNormalizationResult {
  const blocks: MessageBlock[] = [];
  const asyncTasks: UnifiedAsyncTaskState[] = [];

  const envelopeError = coerceError(envelope.error);

  const tools = envelope.tools.map((tool, index) => {
    const chartPrepared = prepareSyncChartToolForDeferredRender(tool, envelope.requestId, index);
    return prepareSyncImageToolForDeferredRender(chartPrepared, envelope.requestId, index);
  });

  // Hoist the `Structured Response Formatter` payload so it can enrich the
  // matching prediction/chart/report block instead of producing duplicate UI.
  const structuredPayload = pickStructuredPayload(tools);

  tools.forEach((tool, index) => {
    const blockId = `${envelope.requestId}-${index}`;
    const toolBlocks = toolToBlocks(tool, blockId, structuredPayload);
    blocks.push(...toolBlocks);

    if (tool.mode === 'async' && (tool as UnifiedAsyncTool).taskId) {
      const taskId = (tool as UnifiedAsyncTool).taskId as string;
      // `local-chart:*` ids are frontend-only (see `prepareSyncChartToolForDeferredRender`);
      // they must never be treated as remote poll targets — `pollAsyncToolTasksWhenEnabled` filters them out.
      asyncTasks.push({
        taskId,
        toolName: tool.toolName,
        type: String(tool.type),
        status: tool.status,
        index,
      });
    }
  });

  if (envelopeError) {
    blocks.push({
      id: `${envelope.requestId}-envelope-error`,
      type: 'error' as MessageBlockType,
      content: {
        title: 'Request failed',
        message: envelopeError.message,
        detail: envelopeError.detail,
        code: envelopeError.code,
        retryable: envelopeError.retryable,
      },
      isComplete: true,
    });
  }

  return {
    requestId: envelope.requestId,
    blocks,
    asyncTasks,
    envelopeError,
  };
}

/**
 * Serializes a unified envelope into the legacy raw-marker text format used
 * by the existing streaming pipeline. Each tool maps to one or more block
 * markers (`---workflow ... ---`, etc.) which are then parsed by
 * `normalizeRawAiResponse`.
 */
export function unifiedResponseToMarkerText(envelope: UnifiedToolResponse): string {
  const result = normalizeUnifiedToolResponse(envelope);
  const parts: string[] = [];

  for (const block of result.blocks) {
    parts.push(serializeBlockForMarkerPipeline(block));
  }

  return parts.join('\n\n');
}

// ─── Per-Tool Conversion ─────────────────────────────────────────────────────

function toolToBlocks(
  tool: UnifiedToolItem,
  baseId: string,
  structured: StructuredToolData | null,
): MessageBlock[] {
  if (tool.status === 'error') {
    return [errorBlock(tool, baseId)];
  }

  switch (canonicalToolType(tool.type)) {
    case 'workflow':
      return workflowToBlocks(tool, baseId);
    case 'reasoning':
      return reasoningToBlocks(tool, baseId);
    case 'chat':
      return chatToBlocks(tool, baseId);
    case 'ocr':
      return ocrToBlocks(tool, baseId);
    case 'prediction':
      return predictionToBlocks(tool, baseId, structured);
    case 'chart':
      return chartToBlocks(tool, baseId);
    case 'report':
      return reportToBlocks(tool, baseId);
    case 'image':
      return imageToBlocks(tool, baseId);
    case 'table':
      return tableToBlocks(tool, baseId);
    case 'code':
      return codeToBlocks(tool, baseId);
    case 'calculator':
      return calculatorToBlocks(tool, baseId);
    case 'math':
      return mathToBlocks(tool, baseId);
    case 'interaction':
      return interactionToBlocks(tool, baseId);
    case 'structured':
      // Already merged into prediction (when present). Otherwise render raw.
      return structuredToBlocks(tool, baseId);
    default:
      return fallbackToBlocks(tool, baseId);
  }
}

// ─── Tool: Workflow ──────────────────────────────────────────────────────────

function workflowToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const data = (tool.data ?? {}) as WorkflowToolData;
  const steps = normalizeWorkflowSteps(data.workflowSteps);
  const title = data.title ?? data.intent ?? tool.toolName;
  const env = toolEnvelopeFromUnifiedItem(tool);

  return [
    {
      id: `${baseId}-workflow`,
      type: 'workflow' as MessageBlockType,
      content: { title, steps, ...toolEnvelopeContentFields(env) },
      isComplete: tool.status === 'success',
    },
  ];
}

function normalizeWorkflowSteps(input: WorkflowToolData['workflowSteps']): WorkflowStep[] {
  if (!Array.isArray(input)) return [];
  return input.map((step, index) => {
    if (typeof step === 'string') {
      return {
        label: step,
        status: index === 0 ? 'active' : 'pending',
      } satisfies WorkflowStep;
    }
    return {
      label: step.label,
      status: step.status ?? 'pending',
      details: step.details,
      timestamp: step.timestamp,
    };
  });
}

// ─── Tool: Reasoning (chain-of-thought) ────────────────────────────────────

function reasoningToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const text = aggregateText(tool);
  if (!text) return [];
  const env = toolEnvelopeFromUnifiedItem(tool);
  const merged = mergeToolEnvelopeIntoContent(text, env);
  return [
    {
      id: `${baseId}-reasoning`,
      type: 'reasoning' as MessageBlockType,
      content: merged.content,
      meta: merged.meta,
      isComplete: isStreamComplete(tool) || tool.status === 'success',
    },
  ];
}

// ─── Tool: Chat / RAG ────────────────────────────────────────────────────────

function chatToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  // If data is an object (not string) and contains a 'type' hint that matches a known
  // tool category (e.g. chart, ocr), we treat this 'chat' tool as that type.
  // This allows models that default to 'chat' output to still trigger rich UI.
  if (tool.data && typeof tool.data === 'object' && !Array.isArray(tool.data)) {
    const obj = tool.data as Record<string, unknown>;
    const hint = String(obj.type || obj.toolType || '')
      .toLowerCase()
      .trim();
    if (hint && hint !== 'chat' && KNOWN_TOOL_TYPES.has(hint)) {
      return toolToBlocks({ ...tool, type: hint as UnifiedToolItem['type'] }, baseId, null);
    }
  }

  const text = aggregateText(tool);
  if (!text) return [];
  const env = toolEnvelopeFromUnifiedItem(tool);
  const merged = mergeToolEnvelopeIntoContent(text, env);

  return [
    {
      id: `${baseId}-chat`,
      type: 'markdown' as MessageBlockType,
      content: merged.content,
      meta: merged.meta,
      isComplete: isStreamComplete(tool),
    },
  ];
}

// ─── Tool: OCR ───────────────────────────────────────────────────────────────

function ocrToBlocks(tool: UnifiedSyncTool | UnifiedToolItem, baseId: string): MessageBlock[] {
  const data = (tool.data ?? {}) as OcrToolData;
  if (!data.text) return [];
  const env = toolEnvelopeFromUnifiedItem(tool as UnifiedToolItem);

  return [
    {
      id: `${baseId}-ocr`,
      type: 'ocr' as MessageBlockType,
      content: { ...data, ...toolEnvelopeContentFields(env) },
      isComplete: tool.status === 'success',
    },
  ];
}

// ─── Tool: Prediction ────────────────────────────────────────────────────────

function predictionToBlocks(
  tool: UnifiedToolItem,
  baseId: string,
  structured: StructuredToolData | null,
): MessageBlock[] {
  const data = (tool.data ?? {}) as PredictionToolData;
  const merged: PredictionToolData = {
    ...data,
    ...mergeStructuredIntoPrediction(structured),
  };

  if (!hasPredictionPayload(merged as Record<string, unknown>)) return fallbackToBlocks(tool, baseId);
  const env = toolEnvelopeFromUnifiedItem(tool);

  return [
    {
      id: `${baseId}-prediction`,
      type: 'prediction' as MessageBlockType,
      content: { ...merged, ...toolEnvelopeContentFields(env) },
      isComplete: tool.status === 'success',
    },
  ];
}

function hasPredictionPayload(data: Record<string, unknown>): boolean {
  if (typeof data.hsCode === 'string' && data.hsCode.trim()) return true;
  const signalKeys = [
    'predictedVolume',
    'label',
    'value',
    'confidence',
    'year',
    'productName',
    'metrics',
  ];
  return signalKeys.some((key) => data[key] !== undefined && data[key] !== null && data[key] !== '');
}

function mergeStructuredIntoPrediction(
  structured: StructuredToolData | null,
): Partial<PredictionToolData> {
  if (!structured) return {};
  const out = structured.formattedOutput;
  if (!out || Array.isArray(out) || typeof out !== 'object') return {};
  const obj = out as Record<string, unknown>;

  const partial: Partial<PredictionToolData> = {};
  if (typeof obj.hsCode === 'string') partial.hsCode = obj.hsCode;
  if (typeof obj.productName === 'string') partial.productName = obj.productName;
  if (typeof obj.category === 'string') partial.category = obj.category;
  return partial;
}

// ─── Tool: Chart ─────────────────────────────────────────────────────────────

function chartToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const data = (tool.data ?? {}) as ChartToolData;
  const env = toolEnvelopeFromUnifiedItem(tool);
  const output =
    data.output && typeof data.output === 'object' && !Array.isArray(data.output)
      ? {
          ...data.output,
          title: data.output.title ?? data.title,
          chartType: data.output.chartType ?? data.chartType,
        }
      : undefined;
  const option =
    data.option && typeof data.option === 'object' && !Array.isArray(data.option)
      ? data.option
      : undefined;
  const echartsOption =
    data.echartsOption &&
    typeof data.echartsOption === 'object' &&
    !Array.isArray(data.echartsOption)
      ? data.echartsOption
      : undefined;

  return [
    {
      id: `${baseId}-chart`,
      type: 'chart' as MessageBlockType,
      content: {
        ...toolEnvelopeContentFields(env),
        title: data.title,
        chartType: data.chartType,
        output,
        ...(option ? { option } : {}),
        ...(echartsOption ? { echartsOption } : {}),
      },
      isComplete: tool.status === 'success',
    },
  ];
}

// ─── Tool: Report ────────────────────────────────────────────────────────────

function reportToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const data = (tool.data ?? {}) as ReportToolData;
  const env = toolEnvelopeFromUnifiedItem(tool);

  return [
    {
      id: `${baseId}-report`,
      type: 'report' as MessageBlockType,
      content: {
        ...toolEnvelopeContentFields(env),
        title: data.title,
        reportUrl: data.reportUrl,
        fileSize: data.fileSize,
        format: data.format,
      },
      isComplete: tool.status === 'success',
    },
  ];
}

// ─── Tool: Image ─────────────────────────────────────────────────────────────

function imageToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const data = (tool.data ?? {}) as ImageToolData & { url?: string; src?: string };
  const env = toolEnvelopeFromUnifiedItem(tool);

  return [
    {
      id: `${baseId}-image`,
      type: 'image' as MessageBlockType,
      content: {
        ...toolEnvelopeContentFields(env),
        prompt: data.prompt,
        imageUrl: data.imageUrl ?? data.url ?? data.src,
        loading: tool.status === 'pending' || tool.status === 'processing',
        error: tool.status === 'error',
      },
      isComplete: tool.status === 'success',
    },
  ];
}

// ─── Tool: Structured ────────────────────────────────────────────────────────

function structuredToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const data = (tool.data ?? {}) as StructuredToolData;
  if (data?.interaction) {
    return interactionToBlocks({ ...tool, type: 'interaction', data: data.interaction }, baseId);
  }
  if (!data?.formattedOutput) return [];
  const env = toolEnvelopeFromUnifiedItem(tool);
  const merged = mergeToolEnvelopeIntoContent(
    { formattedOutput: data.formattedOutput, ...toolEnvelopeContentFields(env) },
    env,
  );

  return [
    {
      id: `${baseId}-structured`,
      type: 'tool_output' as MessageBlockType,
      content: merged.content,
      meta: {
        language: 'json',
        toolName: tool.toolName,
        schema: data.schema,
        view: Array.isArray(data.formattedOutput) ? 'table' : 'cards',
        ...(merged.meta ?? {}),
      },
      isComplete: tool.status === 'success',
    },
  ];
}

function tableToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const env = toolEnvelopeFromUnifiedItem(tool);
  return [
    {
      id: `${baseId}-table`,
      type: 'table' as MessageBlockType,
      content: {
        ...(normalizeToolData('table', tool.data) as Record<string, unknown>),
        ...toolEnvelopeContentFields(env),
      },
      isComplete: tool.status === 'success',
    },
  ];
}

function codeToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const env = toolEnvelopeFromUnifiedItem(tool);
  const data = tool.data && typeof tool.data === 'object' ? (tool.data as Record<string, unknown>) : {};
  const merged = mergeToolEnvelopeIntoContent(normalizeToolData('code', tool.data), env);
  return [
    {
      id: `${baseId}-code`,
      type: 'code' as MessageBlockType,
      content: merged.content,
      meta: {
        language: typeof data.language === 'string' ? data.language : 'text',
        toolName: tool.toolName,
        ...(merged.meta ?? {}),
      },
      isComplete: tool.status === 'success',
    },
  ];
}

function calculatorToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  if (!hasCalculatorPayload(tool.data)) return [];
  const markdown = calculatorDataToMarkdown(tool.data);
  if (!markdown.trim()) return [];
  return [markdownToolBlock(tool, baseId, 'calc', markdown)];
}

function hasCalculatorPayload(data: unknown): boolean {
  if (data === null || data === undefined) return false;
  if (typeof data !== 'object') return String(data).trim().length > 0;
  if (Array.isArray(data)) return data.length > 0;

  const obj = data as Record<string, unknown>;
  return [
    obj.expression,
    obj.result,
    obj.formula,
    obj.note,
    obj.description,
    obj.steps,
  ].some((value) => {
    if (Array.isArray(value)) return value.length > 0;
    if (value === 0) return true;
    return Boolean(value);
  });
}

function mathToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const markdown = mathDataToMarkdown(tool.data);
  if (!markdown.trim()) return [];
  return [markdownToolBlock(tool, baseId, 'formula', markdown)];
}

function markdownToolBlock(
  tool: UnifiedToolItem,
  baseId: string,
  suffix: string,
  content: string,
): MessageBlock {
  return {
    id: `${baseId}-${suffix}`,
    type: 'markdown' as MessageBlockType,
    content,
    isComplete: tool.status === 'success' || isStreamComplete(tool),
  };
}

function interactionToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const env = toolEnvelopeFromUnifiedItem(tool);
  return [
    {
      id: `${baseId}-interaction`,
      type: 'interaction' as MessageBlockType,
      content: {
        ...(normalizeToolData('interaction', tool.data) as Record<string, unknown>),
        ...toolEnvelopeContentFields(env),
      },
      isComplete: false,
    },
  ];
}

// ─── Tool: Fallback ──────────────────────────────────────────────────────────

function fallbackToBlocks(tool: UnifiedToolItem, baseId: string): MessageBlock[] {
  const aggregated = tool.data ?? aggregateText(tool);
  if (aggregated == null || aggregated === '') return [];

  const content = typeof aggregated === 'string' ? aggregated : JSON.stringify(aggregated, null, 2);
  const env = toolEnvelopeFromUnifiedItem(tool);
  const merged = mergeToolEnvelopeIntoContent(content, env);
  return [
    {
      id: `${baseId}-tool-output`,
      type: 'tool_output' as MessageBlockType,
      content: merged.content,
      meta: {
        language: typeof aggregated === 'string' ? 'text' : 'json',
        toolName: tool.toolName,
        ...(merged.meta ?? {}),
      },
      isComplete: tool.status === 'success',
    },
  ];
}

// ─── Tool: Error ─────────────────────────────────────────────────────────────

function errorBlock(tool: UnifiedToolItem, baseId: string): MessageBlock {
  const err = coerceError(tool.error) ?? {
    message: `${tool.toolName} failed`,
  };
  const env = toolEnvelopeFromUnifiedItem(tool);
  return {
    id: `${baseId}-error`,
    type: 'error' as MessageBlockType,
    content: {
      title: tool.toolName,
      message: err.message,
      detail: err.detail,
      code: err.code,
      retryable: err.retryable ?? true,
      ...toolEnvelopeContentFields(env),
    },
    isComplete: true,
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function pickStructuredPayload(tools: UnifiedToolItem[]): StructuredToolData | null {
  const item = tools.find(
    (t) => canonicalToolType(t.type) === 'structured' && t.status === 'success',
  );
  if (!item) return null;
  const data = item.data as StructuredToolData | undefined;
  return data?.formattedOutput ? data : null;
}

function aggregateText(tool: UnifiedToolItem): string {
  if (tool.mode !== 'stream') {
    if (typeof tool.data === 'string') return tool.data;
    if (tool.data && typeof tool.data === 'object') {
      // If it's an object but doesn't have a specific tool type (handled in chatToBlocks),
      // we render it as stringified JSON in the markdown block.
      return JSON.stringify(tool.data, null, 2);
    }
    return '';
  }
  const stream = tool as UnifiedStreamTool;
  if (!Array.isArray(stream.streamChunks)) return '';
  const ordered = [...stream.streamChunks].sort((a, b) => {
    const ai = typeof a.index === 'number' ? a.index : 0;
    const bi = typeof b.index === 'number' ? b.index : 0;
    return ai - bi;
  });
  return ordered.map((c) => c.chunk ?? '').join('');
}

function isStreamComplete(tool: UnifiedToolItem): boolean {
  if (tool.status === 'success') return true;
  if (tool.mode !== 'stream') return false;
  const chunks = (tool as UnifiedStreamTool).streamChunks;
  if (!Array.isArray(chunks) || chunks.length === 0) return false;
  return chunks.some((c) => c.done === true);
}

/**
 * Normalize a task poll JSON body into blocks. Backend may return a full
 * `UnifiedToolResponse` or a single `UnifiedToolItem` for the updated tool row.
 */
export function normalizeTaskPollBody(body: unknown): MessageBlock[] {
  if (isUnifiedToolResponse(body)) {
    return normalizeUnifiedToolResponse(body).blocks;
  }
  if (isProbablyUnifiedToolItem(body)) {
    return toolToBlocks(body, `poll-${uid('tsk')}`, null);
  }
  return [];
}

function isProbablyUnifiedToolItem(value: unknown): value is UnifiedToolItem {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const o = value as Record<string, unknown>;
  return (
    typeof o.toolName === 'string' &&
    typeof o.type === 'string' &&
    typeof o.mode === 'string' &&
    typeof o.status === 'string'
  );
}

const KNOWN_TOOL_TYPES = new Set([
  'workflow',
  'reasoning',
  'chat',
  'ocr',
  'prediction',
  'chart',
  'report',
  'image',
  'structured',
  'table',
  'code',
  'calculator',
  'math',
  'interaction',
  'tool_output',
  'error',
]);

const TOOL_TYPE_ALIASES: Record<string, string> = {
  thinking: 'reasoning',
  thought: 'reasoning',
  chain_of_thought: 'reasoning',
  // chat aliases
  rag: 'chat',
  llm: 'chat',
  message: 'chat',
  // workflow aliases
  plan: 'workflow',
  planner: 'workflow',
  intent: 'workflow',
  steps: 'workflow',
  // prediction aliases
  forecast: 'prediction',
  classification: 'prediction',
  // chart aliases
  graph: 'chart',
  // ocr aliases
  document: 'ocr',
  // report aliases
  pdf: 'report',
  // image aliases
  visual: 'image',
  picture: 'image',
};

/**
 * Resolves a backend-provided tool type to one of the canonical tool types
 * the renderer knows how to dispatch on. Unknown values fall back to
 * `tool_output` (raw rendering) instead of `canonicalizeBlockType` to avoid
 * confusing block-level aliases with tool-level types.
 */
function canonicalToolType(type: string): string {
  const t = String(type || '')
    .toLowerCase()
    .trim();
  if (KNOWN_TOOL_TYPES.has(t)) return t;
  if (TOOL_TYPE_ALIASES[t]) return TOOL_TYPE_ALIASES[t]!;
  // Fall back to the block canonicalizer for legacy aliases like
  // `chart_task`/`report_task` that producers may still emit.
  const blockType = canonicalizeBlockType(t);
  return KNOWN_TOOL_TYPES.has(blockType) ? blockType : 'tool_output';
}

function coerceError(input: unknown): UnifiedToolError | null {
  if (!input) return null;
  if (typeof input === 'string') return { message: input };
  if (typeof input === 'object') {
    const obj = input as Record<string, unknown>;
    if (typeof obj.message === 'string') {
      return {
        message: obj.message,
        code: typeof obj.code === 'string' ? obj.code : undefined,
        detail: typeof obj.detail === 'string' ? obj.detail : undefined,
        retryable: typeof obj.retryable === 'boolean' ? obj.retryable : undefined,
      };
    }
  }
  return null;
}

// ─── Convenience Builders ────────────────────────────────────────────────────

/**
 * Lightweight factory used by mock layers and tests. Generates a fresh
 * `requestId` if one is not provided.
 */
export function buildUnifiedToolResponse(
  partial: Partial<UnifiedToolResponse> & { tools: UnifiedToolItem[] },
): UnifiedToolResponse {
  return {
    requestId: partial.requestId ?? uid('req'),
    mode: partial.mode ?? 'sync',
    status: partial.status ?? deriveEnvelopeStatus(partial.tools),
    tools: partial.tools,
    timestamp: partial.timestamp ?? new Date().toISOString(),
    error: partial.error ?? null,
    meta: partial.meta,
  };
}

function deriveEnvelopeStatus(tools: UnifiedToolItem[]): UnifiedToolResponse['status'] {
  if (tools.some((t) => t.status === 'error')) return 'error';
  if (tools.some((t) => t.status === 'pending' || t.status === 'processing')) {
    return tools.every((t) => t.status === 'pending' || t.status === 'processing')
      ? 'pending'
      : 'partial';
  }
  return 'success';
}
