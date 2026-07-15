import type { MessageSource, MessageStatus } from './chat';

export interface ChatApiIntegrationEphemeralMcp {
  type: 'ephemeral_mcp';
  server_label: string;
  server_url: string;
  allowed_tools?: string[];
  meta?: Record<string, unknown>;
}

export interface ChatApiIntegrationPlugin {
  type: 'plugin';
  id: string;
  allowed_tools?: string[];
  meta?: Record<string, unknown>;
}

export type ChatApiIntegration = ChatApiIntegrationEphemeralMcp | ChatApiIntegrationPlugin;

export interface ChatApiRequest {
  model: string;
  input: string;
  integrations?: ChatApiIntegration[];
  context_length?: number;
  temperature?: number;
  stream?: boolean;
}

export interface ChatApiToolCallProvider {
  type?: 'ephemeral_mcp' | 'plugin' | string;
  server_label?: string;
  plugin_id?: string;
}

export interface ChatApiOutputToolCall {
  type: 'tool_call';
  tool: string;
  arguments?: Record<string, unknown>;
  output?: unknown;
  provider_info?: ChatApiToolCallProvider;
  status?: 'success' | 'pending' | 'processing' | 'error';
  error?: { message?: string; code?: string; detail?: string } | string | null;
}

export interface ChatApiOutputMessage {
  type: 'message';
  content: string;
  role?: 'assistant' | 'system' | 'user';
}

export interface ChatApiOutputReasoning {
  type: 'reasoning';
  content: string;
}

export type ChatApiOutputItem =
  | ChatApiOutputToolCall
  | ChatApiOutputMessage
  | ChatApiOutputReasoning;

export interface ChatApiStats {
  input_tokens?: number;
  total_output_tokens?: number;
  reasoning_output_tokens?: number;
  tokens_per_second?: number;
  time_to_first_token_seconds?: number;
  model_load_time_seconds?: number;
}

export interface ChatApiResponse {
  model_instance_id?: string;
  output: ChatApiOutputItem[];
  stats?: ChatApiStats;
  response_id?: string;
  error?: { message?: string; code?: string; detail?: string } | string | null;
}

export interface ChatApiModel {
  id: string;
  object?: string;
  owned_by?: string;
  loaded?: boolean;
  size?: number;
  format?: string;
  family?: string;
  context_length?: number;
  [key: string]: unknown;
}

export interface ChatApiModelsListResponse {
  data?: ChatApiModel[];
  models?: ChatApiModel[];
  object?: string;
}

export interface ChatApiLoadModelRequest {
  model: string;
  context_length?: number;
  gpu_layers?: number;
  quantization?: string;
  [key: string]: unknown;
}

export interface ChatApiLoadModelResponse {
  ok?: boolean;
  loaded?: boolean;
  model?: ChatApiModel | string;
  error?: { message?: string; code?: string } | string | null;
  [key: string]: unknown;
}

export interface ChatApiDownloadRequest {
  model: string;
  file?: string;
  quantization?: string;
  [key: string]: unknown;
}

export interface ChatApiDownloadResponse {
  job_id?: string;
  ok?: boolean;
  error?: { message?: string; code?: string } | string | null;
  [key: string]: unknown;
}

export interface ChatApiDownloadStatus {
  job_id: string;
  status: 'pending' | 'downloading' | 'completed' | 'error' | 'cancelled' | string;
  progress?: number;
  downloaded_bytes?: number;
  total_bytes?: number;
  error?: { message?: string; code?: string } | string | null;
  [key: string]: unknown;
}

export interface ChatApiHttpConfig {
  baseUrl: string;
  apiToken?: string;
}

export interface ChatApiFetchOptions {
  method?: 'GET' | 'POST' | 'DELETE' | 'PUT' | 'PATCH';
  path: string;
  body?: unknown;
  signal?: AbortSignal;
  accept?: string;
  headers?: Record<string, string>;
}

export interface ChatApiClientConfig {
  baseUrl: string;
  apiToken: string;
  model: string;
  contextLength?: number;
  temperature?: number;
}

export interface ChatApiSendOptions {
  input: string;
  integrations?: ChatApiIntegration[];
  temperature?: number;
  contextLength?: number;
  signal?: AbortSignal;
}

export type ChatApiTransport = 'gdce';

export interface NormalizedChatTableColumn {
  key: string;
  label: string;
}

export interface NormalizedMarkdownBlock {
  type: 'markdown';
  text: string;
}

export interface NormalizedTableBlock {
  type: 'table';
  title?: string;
  columns: NormalizedChatTableColumn[];
  rows: Record<string, string | number | boolean | null>[];
}

export interface NormalizedClarificationBlock {
  type: 'clarification';
  title?: string;
  questions: string[];
}

export interface NormalizedErrorBlock {
  type: 'error';
  message: string;
}

export interface NormalizedChartBlock {
  type: 'chart';
  title?: string;
  data: Record<string, unknown>;
}

export type NormalizedChatContentBlock =
  | NormalizedMarkdownBlock
  | NormalizedTableBlock
  | NormalizedClarificationBlock
  | NormalizedErrorBlock
  | NormalizedChartBlock;

export interface NormalizedChatMessage {
  role: 'assistant';
  content: NormalizedChatContentBlock[];
}

export interface NormalizedChatDebug {
  latency_ms?: number;
  confidence?: 'high' | 'medium' | 'low';
  answer_source?: string;
  metadata?: Record<string, unknown>;
}

export interface NormalizedCitation extends MessageSource {
  id: string;
  label?: string;
  score?: number;
}

export interface NormalizedChatResponse {
  request_id: string;
  session_id: string;
  chat_id?: string;
  project_id?: string | null;
  status: Extract<MessageStatus, 'completed' | 'processing' | 'failed'>;
  intent: string;
  message: NormalizedChatMessage;
  citations: NormalizedCitation[];
  suggestions?: string[];
  debug?: NormalizedChatDebug;
}

export interface ChatApiStreamingConfig {
  baseUrl: string;
  apiToken: string;
  devEmail?: string;
  devPassword?: string;
  model: string;
  contextLength?: number;
  temperature?: number;
  maxHistoryMessages?: number;
  maxHistoryChars?: number;
  defaultIntegrations?: ChatApiIntegration[];
  transport?: ChatApiTransport;
  stream?: boolean;
}

export interface UseChatApiModelsConfig {
  baseUrl: string;
  apiToken?: string;
}
