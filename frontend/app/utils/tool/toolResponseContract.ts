/**
 * Tool / agent response contract (frontend mirror of the API matrix).
 *
 * OpenAI-style LM Studio streams often **do not** emit `UnifiedToolResponse`; polling and
 * envelopes work when the backend returns the v2 envelope or gdce-render JSON with these fields.
 */

import type { MessageBlock } from '~/types/message';
import type { ToolMode, ToolStatus, UnifiedAsyncTool, UnifiedToolItem } from '~/types/unified';

/** Status string stored inside chart/report `content` (LegacyChartTask / ReportTask). */
export type TaskWidgetContentStatus = 'pending' | 'processing' | 'completed' | 'error';

/** Fields merged into block `content` (object blocks) or `meta.tool` (string markdown). */
export interface ToolResponseEnvelope {
  toolName: string;
  /** Original tool type from the API (e.g. workflow, chat, chart). */
  type: string;
  mode: ToolMode;
  /** Raw tool lifecycle status from the API. */
  toolStatus: ToolStatus;
  /**
   * Widget lifecycle field inside `content` for chart/report-style blocks
   * (`pending` | `processing` | `completed` | `error`), not `MessageBlock.status`.
   */
  status: TaskWidgetContentStatus;
  taskId?: string;
}

export const TOOL_RESPONSE_MATRIX = [
  'workflow: sync|stream → workflow',
  'chat (RAG): stream → chat',
  'ocr: sync → ocr',
  'prediction: sync → prediction',
  'report: async → report (+ taskId)',
  'chart: async → chart (+ taskId)',
  'image: async → image (+ taskId)',
  'structured: sync → structured',
  'table: sync → table',
  'code: sync → code',
  'calculator: sync → markdown (formula code blocks)',
  'math: sync → markdown (inline/fenced formulas)',
  'interaction: sync → interaction',
  'tool: sync|async|stream → tool_output',
] as const;

export function mapUnifiedToolStatusToTaskWidgetStatus(
  status: ToolStatus,
): TaskWidgetContentStatus {
  if (status === 'success') return 'completed';
  if (status === 'cancelled' || status === 'error') return 'error';
  if (status === 'processing') return 'processing';
  return 'pending';
}

/** Map API / fence free-text status to MessageBlock.status (top-level block). */
export function mapFenceOrApiStatusToBlockStatus(
  raw: string | undefined,
): NonNullable<MessageBlock['status']> | undefined {
  if (!raw || typeof raw !== 'string') return undefined;
  const s = raw.trim().toLowerCase();
  if (s === 'success' || s === 'completed') return 'completed';
  if (s === 'failed' || s === 'error' || s === 'cancelled') return 'failed';
  if (s === 'processing') return 'processing';
  if (s === 'pending') return 'pending';
  return undefined;
}

export function toolEnvelopeFromUnifiedItem(tool: UnifiedToolItem): ToolResponseEnvelope {
  const taskId = tool.mode === 'async' ? (tool as UnifiedAsyncTool).taskId : undefined;
  return {
    toolName: tool.toolName,
    type: String(tool.type),
    mode: tool.mode,
    toolStatus: tool.status,
    status: mapUnifiedToolStatusToTaskWidgetStatus(tool.status),
    taskId: typeof taskId === 'string' && taskId.trim() ? taskId : undefined,
  };
}

/** Flat record merged into `MessageBlock.content` when content is a plain object. */
export function toolEnvelopeContentFields(envelope: ToolResponseEnvelope): Record<string, unknown> {
  return {
    toolName: envelope.toolName,
    type: envelope.type,
    mode: envelope.mode,
    toolStatus: envelope.toolStatus,
    status: envelope.status,
    ...(envelope.taskId ? { taskId: envelope.taskId } : {}),
  };
}

export function mergeToolEnvelopeIntoContent(
  content: unknown,
  envelope: ToolResponseEnvelope,
): { content: unknown; meta?: Record<string, unknown> } {
  const flat = toolEnvelopeContentFields(envelope);
  if (content && typeof content === 'object' && !Array.isArray(content)) {
    return { content: { ...(content as Record<string, unknown>), ...flat } };
  }
  return {
    content,
    meta: { tool: flat },
  };
}

function coerceToolMode(value: unknown): ToolMode {
  if (value === 'sync' || value === 'async' || value === 'stream') return value;
  return 'sync';
}

function coerceApiStringToToolStatus(value: unknown): ToolStatus {
  if (!value || typeof value !== 'string') return 'pending';
  const s = value.trim().toLowerCase();
  if (s === 'success' || s === 'completed') return 'success';
  if (s === 'processing' || s === 'partial') return 'processing';
  if (s === 'error' || s === 'failed') return 'error';
  if (s === 'cancelled' || s === 'canceled') return 'cancelled';
  if (s === 'pending') return 'pending';
  return 'pending';
}

/**
 * Merge gdce-render JSON **root** fields `mode`, `taskId`, `toolName`, `status` (API string)
 * into `content` when it is a plain object, otherwise under `meta.tool`.
 */
export function mergeFenceRootToolFields(
  raw: Record<string, unknown>,
  blockType: string,
  content: unknown,
): { content: unknown; metaPatch?: Record<string, unknown> } {
  const hasRoot =
    typeof raw.mode === 'string' ||
    typeof raw.taskId === 'string' ||
    typeof raw.toolName === 'string' ||
    raw.status !== undefined;
  if (!hasRoot) return { content };

  const flat: Record<string, unknown> = {};
  if (typeof raw.type === 'string') flat.type = raw.type;
  else flat.type = blockType;
  if (typeof raw.toolName === 'string') flat.toolName = raw.toolName;
  if (typeof raw.mode === 'string') flat.mode = coerceToolMode(raw.mode);
  if (typeof raw.taskId === 'string' && raw.taskId.trim()) flat.taskId = raw.taskId.trim();
  if (raw.status !== undefined) {
    const toolStatus = coerceApiStringToToolStatus(raw.status);
    flat.toolStatus = toolStatus;
    flat.status = mapUnifiedToolStatusToTaskWidgetStatus(toolStatus);
  }

  if (content && typeof content === 'object' && !Array.isArray(content)) {
    return { content: { ...(content as Record<string, unknown>), ...flat } };
  }
  return { content, metaPatch: { tool: flat } };
}
