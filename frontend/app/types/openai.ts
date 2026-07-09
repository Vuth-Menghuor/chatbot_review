import type { UnifiedToolResponse } from './unified';

export type OpenAiRole = 'system' | 'user' | 'assistant' | 'tool' | 'developer';

export interface OpenAiChatMessage {
  role: OpenAiRole;
  content: string | OpenAiChatContentPart[];
  name?: string;
  tool_call_id?: string;
  tool_calls?: OpenAiToolCall[];
}

export interface OpenAiChatContentPart {
  type: 'text' | 'image_url' | string;
  text?: string;
  image_url?: { url: string; detail?: string };
  [key: string]: unknown;
}

export interface OpenAiToolCall {
  id: string;
  type: 'function' | string;
  function: { name: string; arguments: string };
}

export interface OpenAiChatCompletionRequest {
  model: string;
  messages: OpenAiChatMessage[];
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  stream?: boolean;
  stop?: string | string[];
  tools?: Array<{
    type: 'function';
    function: { name: string; description?: string; parameters?: Record<string, unknown> };
  }>;
  tool_choice?: 'auto' | 'none' | { type: 'function'; function: { name: string } };
  [key: string]: unknown;
}

export interface OpenAiUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface OpenAiChatCompletionChoice {
  index?: number;
  message?: OpenAiChatMessage;
  finish_reason?: 'stop' | 'length' | 'tool_calls' | 'content_filter' | string | null;
}

export interface OpenAiChatCompletionResponse {
  id?: string;
  object?: string;
  created?: number;
  model?: string;
  choices?: OpenAiChatCompletionChoice[];
  usage?: OpenAiUsage;
  error?: { message?: string; code?: string; type?: string } | string | null;
  [key: string]: unknown;
}

export interface OpenAiChatCompletionDelta {
  role?: OpenAiRole;
  content?: string;
  tool_calls?: Array<Partial<OpenAiToolCall> & { index?: number }>;
}

export interface OpenAiChatCompletionStreamChoice {
  index?: number;
  delta?: OpenAiChatCompletionDelta;
  finish_reason?: string | null;
}

export interface OpenAiChatCompletionStreamChunk {
  id?: string;
  object?: string;
  created?: number;
  model?: string;
  choices?: OpenAiChatCompletionStreamChoice[];
  [key: string]: unknown;
}

export interface OpenAiChatStreamAggregatorState {
  textByIndex: Map<number, string>;
  toolCallsByIndex: Map<number, Map<number, OpenAiToolCall>>;
  finishByIndex: Map<number, string | null>;
  lastChunk: OpenAiChatCompletionStreamChunk | null;
}

export interface OpenAiResponseInputText {
  role: OpenAiRole;
  content: string | OpenAiChatContentPart[];
}

export interface OpenAiResponseRequest {
  model: string;
  input: string | OpenAiResponseInputText[];
  temperature?: number;
  max_output_tokens?: number;
  stream?: boolean;
  [key: string]: unknown;
}

export interface OpenAiResponseOutputItem {
  type: 'message' | 'tool_call' | string;
  content?: Array<{ type: 'output_text' | string; text?: string }>;
  name?: string;
  arguments?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface OpenAiResponseResult {
  id?: string;
  object?: 'response' | string;
  model?: string;
  output?: OpenAiResponseOutputItem[];
  output_text?: string;
  usage?: OpenAiUsage;
  error?: { message?: string; code?: string } | string | null;
  [key: string]: unknown;
}

export interface OpenAiCompletionRequest {
  model: string;
  prompt: string | string[];
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  stop?: string | string[];
  [key: string]: unknown;
}

export interface OpenAiCompletionChoice {
  index?: number;
  text?: string;
  finish_reason?: string | null;
}

export interface OpenAiCompletionResponse {
  id?: string;
  object?: string;
  created?: number;
  model?: string;
  choices?: OpenAiCompletionChoice[];
  usage?: OpenAiUsage;
  [key: string]: unknown;
}

export interface OpenAiEmbeddingRequest {
  model: string;
  input: string | string[];
  encoding_format?: 'float' | 'base64';
  [key: string]: unknown;
}

export interface OpenAiEmbeddingItem {
  object?: 'embedding' | string;
  index?: number;
  embedding: number[] | string;
}

export interface OpenAiEmbeddingResponse {
  object?: string;
  data?: OpenAiEmbeddingItem[];
  model?: string;
  usage?: OpenAiUsage;
  [key: string]: unknown;
}

export interface UseChatApiOpenAiConfig {
  baseUrl: string;
  apiToken?: string;
  defaultModel?: string;
}

export interface OpenAiChatStreamCallbacks {
  onText?: (deltaText: string, chunk: OpenAiChatCompletionStreamChunk) => void;
  onChunk?: (chunk: OpenAiChatCompletionStreamChunk, state: OpenAiChatStreamAggregatorState) => void;
  onDone?: (final: UnifiedToolResponse, state: OpenAiChatStreamAggregatorState) => void;
}

export interface OpenAiChatStreamHandle {
  result: Promise<UnifiedToolResponse>;
  state: OpenAiChatStreamAggregatorState;
}
