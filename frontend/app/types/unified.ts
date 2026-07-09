import type { ChatApiResponse } from './chatApi';
import type { MessageBlock } from './chat';
import type { ChartKind, ChartOutput, WorkflowStep } from './renderer';

export type RequestMode = 'sync' | 'stream' | 'async';

export type RequestStatus = 'success' | 'pending' | 'error' | 'partial';

export type ToolMode = 'sync' | 'stream' | 'async';

export type ToolStatus = 'success' | 'pending' | 'processing' | 'error' | 'cancelled';

export type UnifiedToolType =
  | 'workflow'
  | 'chat'
  | 'ocr'
  | 'prediction'
  | 'report'
  | 'chart'
  | 'image'
  | 'structured'
  | 'reasoning'
  | 'table'
  | 'code'
  | 'calculator'
  | 'math'
  | 'interaction'
  | 'tool_output'
  | 'error'
  | (string & {});

export interface UnifiedStreamChunk {
  chunk: string;
  done?: boolean;
  index?: number;
  meta?: Record<string, unknown>;
}

export interface UnifiedToolError {
  code?: string;
  message: string;
  detail?: string;
  retryable?: boolean;
}

interface UnifiedToolBase {
  toolName: string;
  type: UnifiedToolType;
  mode: ToolMode;
  status: ToolStatus;
  meta?: Record<string, unknown>;
  error?: UnifiedToolError | string | null;
}

export interface UnifiedSyncTool extends UnifiedToolBase {
  mode: 'sync';
  data?: unknown;
}

export interface UnifiedStreamTool extends UnifiedToolBase {
  mode: 'stream';
  streamChunks?: UnifiedStreamChunk[];
  data?: unknown;
}

export interface UnifiedAsyncTool extends UnifiedToolBase {
  mode: 'async';
  taskId?: string;
  data?: unknown;
}

export type UnifiedToolItem = UnifiedSyncTool | UnifiedStreamTool | UnifiedAsyncTool;

export interface UnifiedToolResponse {
  requestId: string;
  mode: RequestMode;
  status: RequestStatus;
  tools: UnifiedToolItem[];
  timestamp?: string;
  error?: UnifiedToolError | string | null;
  meta?: Record<string, unknown>;
}

export interface UnifiedAsyncTaskState {
  taskId: string;
  toolName: string;
  type: string;
  status: ToolStatus;
  index: number;
}

export interface UnifiedNormalizationResult {
  requestId: string;
  blocks: MessageBlock[];
  asyncTasks: UnifiedAsyncTaskState[];
  envelopeError: UnifiedToolError | null;
}

export interface WorkflowToolData {
  intent?: string;
  title?: string;
  workflowSteps?: Array<string | WorkflowStep>;
}

export interface OcrToolData {
  text: string;
  language?: string;
  confidence?: number;
  pages?: number;
  fields?: Record<string, string>;
}

export interface PredictionToolData {
  hsCode?: string;
  productName?: string;
  category?: string;
  confidence?: number;
  reason?: string;
  evidence?: string[];
  predictedVolume?: number;
  year?: number;
  label?: string;
  value?: string | number;
  unit?: string;
  sourceName?: string;
  sourceUrl?: string;
}

export interface ChartToolData {
  title?: string;
  chartType?: ChartKind;
  output?: ChartOutput;
  /** Raw ECharts option when the API does not emit `ChartOutput`. */
  option?: Record<string, unknown>;
  /** Alias some backends use instead of `option` (same semantics as `content.echartsOption`). */
  echartsOption?: Record<string, unknown>;
}

export interface ReportToolData {
  title?: string;
  reportUrl?: string;
  fileSize?: string;
  format?: string;
}

export interface ImageToolData {
  prompt?: string;
  imageUrl?: string;
}

export interface StructuredToolData {
  formattedOutput: Record<string, unknown> | unknown[];
  schema?: string;
  interaction?: InteractionToolData;
}

export type InteractionFieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'checkbox'
  | 'select'
  | 'radio'
  | 'date'
  | 'file';

export interface InteractionFieldOption {
  label: string;
  value: string | number | boolean;
}

export interface InteractionField {
  name: string;
  label?: string;
  type?: InteractionFieldType;
  default?: unknown;
  required?: boolean;
  placeholder?: string;
  options?: InteractionFieldOption[];
}

export interface InteractionAction {
  id: string;
  label?: string;
  primary?: boolean;
}

export interface InteractionToolData {
  kind?: 'form' | 'confirm' | 'select' | 'upload';
  title?: string;
  description?: string;
  requestId?: string;
  toolName?: string;
  fields?: InteractionField[];
  actions?: InteractionAction[];
}

export interface ChatApiCallResult {
  unified: UnifiedToolResponse;
  raw: ChatApiResponse;
}
