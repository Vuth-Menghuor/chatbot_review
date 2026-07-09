/**
 * Chat API (`/api/v1/chat`) → `UnifiedToolResponse` adapter.
 *
 * This adapter maps AI response payloads into a `UnifiedToolResponse`
 * envelope, which the renderer already knows how to consume.
 */

import type {
  ChatApiOutputItem,
  ChatApiOutputMessage,
  ChatApiOutputReasoning,
  ChatApiOutputToolCall,
  ChatApiResponse,
  OpenAiChatCompletionChoice,
  OpenAiChatCompletionResponse,
  OpenAiChatCompletionStreamChunk,
  OpenAiChatStreamAggregatorState,
  OpenAiResponseOutputItem,
  OpenAiResponseResult,
  OpenAiToolCall,
  ToolStatus,
  UnifiedToolItem,
  UnifiedToolResponse,
} from '~/types/message';
import { tryParseJsonLike } from '~/utils/json';
import { uid } from '~/utils/id';
import { buildUnifiedToolResponse, isUnifiedToolResponse } from '~/utils/tool';

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Convert a full Chat API response payload into a `UnifiedToolResponse`
 * envelope.
 */
export function chatApiResponseToUnified(
  response: ChatApiResponse,
  options: { requestId?: string; timestamp?: string } = {},
): UnifiedToolResponse {
  const tools: UnifiedToolItem[] = [];

  for (const item of response.output ?? []) {
    const tool = outputItemToTool(item);
    if (tool) tools.push(tool);
  }

  const envelopeError = coerceChatApiError(response.error);

  const unwrapped = tryUnwrapUnifiedEnvelopeFromOpenAiTools(tools);
  if (unwrapped) {
    return {
      ...unwrapped,
      requestId: pickRequestId(unwrapped.requestId, options.requestId, response.response_id),
      timestamp: unwrapped.timestamp ?? options.timestamp,
      error: unwrapped.error ?? envelopeError,
      meta: mergeEnvelopeMeta(unwrapped.meta, {
        ...(response.stats ? { stats: response.stats } : {}),
        modelInstanceId: response.model_instance_id,
      }),
    };
  }

  return buildUnifiedToolResponse({
    requestId: options.requestId ?? response.response_id ?? undefined,
    mode: 'sync',
    tools,
    timestamp: options.timestamp,
    error: envelopeError,
    meta: response.stats
      ? { stats: response.stats, modelInstanceId: response.model_instance_id }
      : { modelInstanceId: response.model_instance_id },
  });
}

/**
 * Type guard for Chat API responses.
 */
export function isChatApiResponse(value: unknown): value is ChatApiResponse {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const obj = value as Record<string, unknown>;
  return Array.isArray(obj.output) && obj.output.every(isChatApiOutputItem);
}

function isChatApiOutputItem(value: unknown): value is ChatApiOutputItem {
  if (!value || typeof value !== 'object') return false;
  const t = (value as Record<string, unknown>).type;
  return t === 'tool_call' || t === 'message' || t === 'reasoning';
}

// ─── Per-Item Conversion ─────────────────────────────────────────────────────

function outputItemToTool(item: ChatApiOutputItem): UnifiedToolItem | null {
  if (item.type === 'message') return messageToTool(item);
  if (item.type === 'tool_call') return toolCallToTool(item);
  if (item.type === 'reasoning') return reasoningToTool(item);
  return null;
}

function reasoningToTool(item: ChatApiOutputReasoning): UnifiedToolItem | null {
  const text = typeof item.content === 'string' ? item.content : '';
  if (!text) return null;
  return {
    toolName: 'Reasoning',
    type: 'reasoning',
    mode: 'sync',
    status: 'success',
    data: text,
  } as UnifiedToolItem;
}

function messageToTool(item: ChatApiOutputMessage): UnifiedToolItem | null {
  const text = typeof item.content === 'string' ? item.content : '';
  if (!text) return null;
  return {
    toolName: 'Assistant Message',
    type: 'chat',
    mode: 'sync',
    status: 'success',
    data: text,
  };
}

function toolCallToTool(item: ChatApiOutputToolCall): UnifiedToolItem {
  const canonical = canonicalizeChatApiTool(item.tool);
  const status = coerceToolStatus(item.status);
  const error = coerceChatApiError(item.error);
  const providerLabel =
    item.provider_info?.server_label ??
    item.provider_info?.plugin_id ??
    item.provider_info?.type ??
    null;

  const meta: Record<string, unknown> = {};
  if (item.arguments) meta.arguments = item.arguments;
  if (item.provider_info) meta.provider = item.provider_info;
  if (providerLabel) meta.providerLabel = providerLabel;

  const data = mapToolOutputToData(canonical, item);

  return {
    toolName: humanizeToolName(item.tool),
    type: canonical,
    mode: 'sync',
    status,
    data,
    meta: Object.keys(meta).length ? meta : undefined,
    error,
  } as UnifiedToolItem;
}

// ─── Tool-Name Canonicalization ──────────────────────────────────────────────

const NAME_PATTERNS: Array<{ test: RegExp; type: string }> = [
  { test: /^(model_)?search$/i, type: 'tool_output' },
  { test: /(^|_)(navigate|browser|browse|fetch|crawl)/i, type: 'tool_output' },
  { test: /^ocr/i, type: 'ocr' },
  { test: /(^|_)ocr(_|$)/i, type: 'ocr' },
  { test: /(^|_)chart(_|$)/i, type: 'chart' },
  { test: /(^|_)graph(_|$)/i, type: 'chart' },
  { test: /(^|_)report(_|$)/i, type: 'report' },
  { test: /(^|_)image(_|$)/i, type: 'image' },
  { test: /(^|_)predict(ion)?(_|$)/i, type: 'prediction' },
  { test: /(^|_)classif(y|ication)(_|$)/i, type: 'prediction' },
  { test: /(^|_)workflow(_|$)/i, type: 'workflow' },
  { test: /(^|_)plan(ner)?(_|$)/i, type: 'workflow' },
  { test: /(^|_)structured(_|$)/i, type: 'structured' },
  { test: /(^|_)table(_|$)/i, type: 'table' },
  { test: /(^|_)code(_|$)/i, type: 'code' },
  { test: /(^|_)calc(ulator)?(_|$)/i, type: 'calculator' },
  { test: /(^|_)math(_|$)/i, type: 'math' },
  { test: /(^|_)interaction(_|$)/i, type: 'interaction' },
  { test: /(^|_)user_input(_|$)/i, type: 'interaction' },
  { test: /(^|_)chat(_|$)/i, type: 'chat' },
  { test: /(^|_)markdown(_|$)/i, type: 'chat' },
];

export function canonicalizeChatApiTool(toolName: string): string {
  const name = String(toolName || '')
    .toLowerCase()
    .trim();
  if (!name) return 'tool_output';
  for (const { test, type } of NAME_PATTERNS) {
    if (test.test(name)) return type;
  }
  return 'tool_output';
}

function humanizeToolName(toolName: string): string {
  if (!toolName) return 'Tool';
  return toolName.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── Output → `data` Mapping ─────────────────────────────────────────────────

function mapToolOutputToData(canonical: string, item: ChatApiOutputToolCall): unknown {
  const raw = item.output;

  switch (canonical) {
    case 'ocr': {
      if (typeof raw === 'string') return { text: raw };
      if (raw && typeof raw === 'object') return raw;
      return { text: '' };
    }
    case 'chart': {
      if (raw && typeof raw === 'object') return raw;
      return { title: humanizeToolName(item.tool) };
    }
    case 'image': {
      if (typeof raw === 'string') {
        return /^https?:\/\//.test(raw)
          ? { imageUrl: raw, prompt: extractPromptArg(item) }
          : { prompt: raw };
      }
      if (raw && typeof raw === 'object') return raw;
      return { prompt: extractPromptArg(item) };
    }
    case 'report': {
      if (typeof raw === 'string' && /^https?:\/\//.test(raw)) return { reportUrl: raw };
      if (raw && typeof raw === 'object') return raw;
      return { title: humanizeToolName(item.tool) };
    }
    case 'prediction': {
      if (raw && typeof raw === 'object') return raw;
      return { hsCode: typeof raw === 'string' ? raw : '' };
    }
    case 'workflow': {
      if (raw && typeof raw === 'object' && 'workflowSteps' in (raw as object)) return raw;
      const steps = Array.isArray(raw) ? raw : null;
      return {
        intent: humanizeToolName(item.tool),
        workflowSteps: steps ?? [],
      };
    }
    case 'structured': {
      if (raw && typeof raw === 'object') return { formattedOutput: raw };
      return { formattedOutput: { value: raw } };
    }
    case 'table':
    case 'code':
    case 'calculator':
    case 'math':
    case 'interaction': {
      return raw;
    }
    default: {
      if (typeof raw === 'string') return raw;
      if (raw == null) return '';
      return raw;
    }
  }
}

function extractPromptArg(item: ChatApiOutputToolCall): string | undefined {
  const args = item.arguments;
  if (!args) return undefined;
  const candidate =
    (typeof args.prompt === 'string' && args.prompt) ||
    (typeof args.query === 'string' && args.query) ||
    (typeof args.text === 'string' && args.text);
  return candidate || undefined;
}

// ─── Status / Error Coercion ─────────────────────────────────────────────────

function coerceToolStatus(input: ChatApiOutputToolCall['status']): ToolStatus {
  if (input === 'pending') return 'pending';
  if (input === 'processing') return 'processing';
  if (input === 'error') return 'error';
  return 'success';
}

function coerceChatApiError(
  input: ChatApiResponse['error'] | ChatApiOutputToolCall['error'],
): UnifiedToolResponse['error'] {
  if (!input) return null;
  if (typeof input === 'string') return { message: input };
  if (typeof input === 'object') {
    const obj = input as Record<string, unknown>;
    if (typeof obj.message === 'string') {
      return {
        message: obj.message,
        code: typeof obj.code === 'string' ? obj.code : undefined,
        detail: typeof obj.detail === 'string' ? obj.detail : undefined,
      };
    }
  }
  return null;
}

// ─── OpenAI-Compatible Adapters ──────────────────────────────────────────────

function pickRequestId(
  primary: string | undefined,
  ...fallbacks: Array<string | undefined>
): string {
  if (typeof primary === 'string' && primary.trim()) return primary.trim();
  for (const f of fallbacks) {
    if (typeof f === 'string' && f.trim()) return f.trim();
  }
  return uid('req');
}

function mergeEnvelopeMeta(
  existing: UnifiedToolResponse['meta'],
  patch: Record<string, unknown>,
): Record<string, unknown> | undefined {
  const base =
    existing && typeof existing === 'object' && !Array.isArray(existing)
      ? { ...(existing as Record<string, unknown>) }
      : {};
  const merged = { ...base, ...patch };
  return Object.keys(merged).length ? merged : undefined;
}

/**
 * LM Studio / OpenAI often return the v2 `UnifiedToolResponse` JSON as plain assistant
 * `content` (sometimes wrapped in ```json). Without unwrapping, the adapter would emit a
 * single `chat` tool carrying that string, and the UI would show a code block instead of charts.
 */
function stripOuterMarkdownJsonFence(raw: string): string {
  let s = raw.trim();
  if (!s.startsWith('```')) return s;
  const firstNl = s.indexOf('\n');
  if (firstNl === -1) return s;
  s = s.slice(firstNl + 1);
  const close = s.lastIndexOf('\n```');
  if (close >= 0) return s.slice(0, close).trim();
  const close2 = s.lastIndexOf('```');
  if (close2 >= 0) return s.slice(0, close2).trim();
  return s.trim();
}

function tryParseUnifiedEnvelopeFromAssistantText(text: string): UnifiedToolResponse | null {
  const stripped = stripOuterMarkdownJsonFence(text).trim();
  if (!stripped.startsWith('{')) return null;
  if (!stripped.includes('"requestId"') || !stripped.includes('"tools"')) return null;
  const parsed = tryParseJsonLike(stripped);
  return isUnifiedToolResponse(parsed) ? parsed : null;
}

/**
 * When the model's entire reply is one v2 envelope, use it directly instead of a `chat` tool.
 */
function tryUnwrapUnifiedEnvelopeFromOpenAiTools(
  tools: UnifiedToolItem[],
): UnifiedToolResponse | null {
  // Find the first 'chat' tool that contains a valid UnifiedToolResponse JSON.
  // We allow other tools (like 'reasoning') to exist alongside it; they will
  // be replaced by the contents of the unwrapped envelope.
  const chatTool = tools.find(
    (t) => t.type === 'chat' && t.status === 'success' && typeof t.data === 'string',
  );
  if (!chatTool) return null;

  const raw = chatTool.data as string;
  return tryParseUnifiedEnvelopeFromAssistantText(raw);
}

/**
 * Convert an OpenAI-compatible `chat.completion` response into a
 * `UnifiedToolResponse`.
 */
export function openAiChatCompletionToUnified(
  response: OpenAiChatCompletionResponse,
  options: { requestId?: string; timestamp?: string } = {},
): UnifiedToolResponse {
  const tools: UnifiedToolItem[] = [];

  for (const choice of response.choices ?? []) {
    pushChoiceTools(tools, choice);
  }

  const envelope = tryUnwrapUnifiedEnvelopeFromOpenAiTools(tools);
  if (envelope) {
    return {
      ...envelope,
      requestId: pickRequestId(envelope.requestId, options.requestId, response.id),
      timestamp: envelope.timestamp ?? options.timestamp,
      error: envelope.error ?? coerceChatApiError(response.error as ChatApiResponse['error']),
      meta: mergeEnvelopeMeta(envelope.meta, {
        model: response.model,
        usage: response.usage,
        object: response.object,
      }),
    };
  }

  return buildUnifiedToolResponse({
    requestId: options.requestId ?? response.id,
    mode: 'sync',
    tools,
    timestamp: options.timestamp,
    error: coerceChatApiError(response.error as ChatApiResponse['error']),
    meta: {
      model: response.model,
      usage: response.usage,
      object: response.object,
    },
  });
}

/**
 * Convert a single (non-streamed) OpenAI `chat.completion` choice into one
 * or more unified tool items.
 */
export function pushChoiceTools(
  tools: UnifiedToolItem[],
  choice: OpenAiChatCompletionChoice,
): void {
  const message = choice.message;
  if (!message) return;

  if (message.tool_calls?.length) {
    for (const call of message.tool_calls) {
      tools.push(toolCallFromOpenAi(call));
    }
  }

  const text = stringifyOpenAiContent(message.content);
  if (text) {
    tools.push({
      toolName: 'Assistant Message',
      type: 'chat',
      mode: 'sync',
      status: 'success',
      data: text,
    });
  }
}

function toolCallFromOpenAi(call: OpenAiToolCall): UnifiedToolItem {
  const name = call.function?.name ?? 'tool';
  const canonical = canonicalizeChatApiTool(name);
  let parsedArgs: unknown = call.function?.arguments;
  if (typeof parsedArgs === 'string' && parsedArgs.trim().startsWith('{')) {
    try {
      parsedArgs = JSON.parse(parsedArgs);
    } catch {
      // keep raw string
    }
  }
  return {
    toolName: humanizeToolName(name),
    type: canonical,
    mode: 'sync',
    status: 'success',
    data: mapToolOutputToData(canonical, {
      type: 'tool_call',
      tool: name,
      arguments:
        typeof parsedArgs === 'object' && parsedArgs
          ? (parsedArgs as Record<string, unknown>)
          : undefined,
      output: parsedArgs,
    }),
    meta: { source: 'openai_chat_completions', toolCallId: call.id },
  } as UnifiedToolItem;
}

function stringifyOpenAiContent(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (!part || typeof part !== 'object' || Array.isArray(part)) return '';
        const p = part as Record<string, unknown>;
        if (typeof p.text === 'string') return p.text;
        if ('text' in p && p.text != null) return String(p.text);
        return '';
      })
      .join('');
  }
  return '';
}

// ─── OpenAI Stream-Chunk Aggregation ────────────────────────────────────────

export function createOpenAiChatStreamAggregator(): OpenAiChatStreamAggregatorState {
  return {
    textByIndex: new Map(),
    toolCallsByIndex: new Map(),
    finishByIndex: new Map(),
    lastChunk: null,
  };
}

export function applyOpenAiChatStreamChunk(
  state: OpenAiChatStreamAggregatorState,
  chunk: OpenAiChatCompletionStreamChunk,
): { deltaText: string } {
  state.lastChunk = chunk;
  let deltaText = '';

  for (const choice of chunk.choices ?? []) {
    const idx = choice.index ?? 0;
    const delta = choice.delta ?? {};
    if (typeof delta.content === 'string' && delta.content) {
      deltaText += delta.content;
      state.textByIndex.set(idx, (state.textByIndex.get(idx) ?? '') + delta.content);
    }
    if (delta.tool_calls?.length) {
      let bucket = state.toolCallsByIndex.get(idx);
      if (!bucket) {
        bucket = new Map();
        state.toolCallsByIndex.set(idx, bucket);
      }
      for (const tc of delta.tool_calls) {
        const tcIdx = tc.index ?? 0;
        const existing: OpenAiToolCall = bucket.get(tcIdx) ?? {
          id: tc.id ?? `${idx}-${tcIdx}`,
          type: tc.type ?? 'function',
          function: { name: '', arguments: '' },
        };
        if (tc.id) existing.id = tc.id;
        if (tc.type) existing.type = tc.type;
        if (tc.function?.name) existing.function.name += tc.function.name;
        if (tc.function?.arguments) existing.function.arguments += tc.function.arguments;
        bucket.set(tcIdx, existing);
      }
    }
    if (choice.finish_reason !== undefined) {
      state.finishByIndex.set(idx, choice.finish_reason ?? null);
    }
  }

  return { deltaText };
}

export function finalizeOpenAiChatStream(
  state: OpenAiChatStreamAggregatorState,
  options: { requestId?: string; timestamp?: string } = {},
): UnifiedToolResponse {
  const tools: UnifiedToolItem[] = [];
  const indices = new Set<number>([...state.textByIndex.keys(), ...state.toolCallsByIndex.keys()]);
  const sortedIndices = [...indices].sort((a, b) => a - b);

  for (const idx of sortedIndices) {
    const toolCalls = [...(state.toolCallsByIndex.get(idx)?.values() ?? [])];
    for (const call of toolCalls) {
      tools.push(toolCallFromOpenAi(call));
    }
    const text = state.textByIndex.get(idx);
    if (text) {
      tools.push({
        toolName: 'Assistant Message',
        type: 'chat',
        mode: 'sync',
        status: 'success',
        data: text,
      });
    }
  }

  const envelope = tryUnwrapUnifiedEnvelopeFromOpenAiTools(tools);
  if (envelope) {
    return {
      ...envelope,
      requestId: pickRequestId(envelope.requestId, options.requestId, state.lastChunk?.id),
      timestamp: envelope.timestamp ?? options.timestamp,
      error: envelope.error ?? null,
      meta: mergeEnvelopeMeta(envelope.meta, {
        model: state.lastChunk?.model,
        object: state.lastChunk?.object,
        finish_reasons: Object.fromEntries(state.finishByIndex.entries()),
        source: 'openai_chat_completions_stream',
      }),
    };
  }

  return buildUnifiedToolResponse({
    requestId: options.requestId ?? state.lastChunk?.id,
    mode: 'sync',
    tools,
    timestamp: options.timestamp,
    error: null,
    meta: {
      model: state.lastChunk?.model,
      object: state.lastChunk?.object,
      finish_reasons: Object.fromEntries(state.finishByIndex.entries()),
      source: 'openai_chat_completions_stream',
    },
  });
}

// ─── OpenAI `/v1/responses` Adapter ──────────────────────────────────────────

export function openAiResponsesToUnified(
  response: OpenAiResponseResult,
  options: { requestId?: string; timestamp?: string } = {},
): UnifiedToolResponse {
  const tools: UnifiedToolItem[] = [];

  for (const item of response.output ?? []) {
    const tool = openAiResponseItemToTool(item);
    if (tool) tools.push(tool);
  }

  if (!tools.length && response.output_text) {
    tools.push({
      toolName: 'Assistant Message',
      type: 'chat',
      mode: 'sync',
      status: 'success',
      data: response.output_text,
    });
  }

  const envelope = tryUnwrapUnifiedEnvelopeFromOpenAiTools(tools);
  if (envelope) {
    return {
      ...envelope,
      requestId: pickRequestId(envelope.requestId, options.requestId, response.id),
      timestamp: envelope.timestamp ?? options.timestamp,
      error: envelope.error ?? coerceChatApiError(response.error as ChatApiResponse['error']),
      meta: mergeEnvelopeMeta(envelope.meta, {
        model: response.model,
        usage: response.usage,
        source: 'openai_responses',
      }),
    };
  }

  return buildUnifiedToolResponse({
    requestId: options.requestId ?? response.id,
    mode: 'sync',
    tools,
    timestamp: options.timestamp,
    error: coerceChatApiError(response.error as ChatApiResponse['error']),
    meta: { model: response.model, usage: response.usage, source: 'openai_responses' },
  });
}

function openAiResponseItemToTool(item: OpenAiResponseOutputItem): UnifiedToolItem | null {
  if (item.type === 'message') {
    const text = (item.content ?? [])
      .map((part) => (part && typeof part === 'object' ? String(part.text ?? '') : ''))
      .join('');
    if (!text) return null;
    return {
      toolName: 'Assistant Message',
      type: 'chat',
      mode: 'sync',
      status: 'success',
      data: text,
    };
  }
  if (item.type === 'tool_call' && item.name) {
    const canonical = canonicalizeChatApiTool(item.name);
    return {
      toolName: humanizeToolName(item.name),
      type: canonical,
      mode: 'sync',
      status: 'success',
      data: mapToolOutputToData(canonical, {
        type: 'tool_call',
        tool: item.name,
        arguments: item.arguments,
        output: item.arguments,
      }),
      meta: { source: 'openai_responses' },
    } as UnifiedToolItem;
  }
  return null;
}
