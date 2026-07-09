/**
 * Chat API OpenAI-compatible composable.
 */

import type {
  ChatApiHttpConfig,
  OpenAiChatCompletionRequest,
  OpenAiChatCompletionResponse,
  OpenAiChatCompletionStreamChunk,
  OpenAiChatStreamCallbacks,
  OpenAiChatStreamHandle,
  OpenAiCompletionRequest,
  OpenAiCompletionResponse,
  OpenAiEmbeddingRequest,
  OpenAiEmbeddingResponse,
  OpenAiResponseRequest,
  OpenAiResponseResult,
  UnifiedToolResponse,
  UseChatApiOpenAiConfig,
} from '~/types/message';
import {
  applyOpenAiChatStreamChunk,
  createOpenAiChatStreamAggregator,
  finalizeOpenAiChatStream,
  openAiChatCompletionToUnified,
  openAiResponsesToUnified,
} from './chatApiAdapter';
import {
  buildChatApiHeaders,
  buildChatApiUrl,
  chatApiFetch,
  chatApiFetchJson,
} from './chatApiHttp';
import { parseSseFrame } from '~/utils/stream';

export { ChatApiRequestError } from './chatApiHttp';

export function useChatApiOpenAi(config: UseChatApiOpenAiConfig) {
  if (!config.baseUrl) throw new Error('Chat API base URL is not configured');
  const http: ChatApiHttpConfig = { baseUrl: config.baseUrl, apiToken: config.apiToken };

  function withDefaultModel<T extends { model?: string }>(body: T): T {
    if (body.model) return body;
    if (!config.defaultModel) {
      throw new Error('Chat API OpenAI client: no model specified and no defaultModel configured');
    }
    return { ...body, model: config.defaultModel };
  }

  // ── Chat completions ──────────────────────────────────────────────────────

  async function chatCompletion(
    body: OpenAiChatCompletionRequest,
    signal?: AbortSignal,
  ): Promise<{ raw: OpenAiChatCompletionResponse; unified: UnifiedToolResponse }> {
    const requestBody = withDefaultModel({ ...body, stream: false });
    const raw = await chatApiFetchJson<OpenAiChatCompletionResponse>(http, {
      path: '/v1/chat/completions',
      body: requestBody,
      signal,
    });
    return { raw, unified: openAiChatCompletionToUnified(raw) };
  }

  function chatCompletionStream(
    body: OpenAiChatCompletionRequest,
    callbacks: OpenAiChatStreamCallbacks = {},
    signal?: AbortSignal,
  ): OpenAiChatStreamHandle {
    const state = createOpenAiChatStreamAggregator();
    const requestBody = withDefaultModel({ ...body, stream: true });

    const result = (async (): Promise<UnifiedToolResponse> => {
      const url = buildChatApiUrl(config.baseUrl, '/v1/chat/completions');
      const headers = buildChatApiHeaders(http, undefined, 'text/event-stream');
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
        signal,
      });
      if (!response.ok || !response.body) {
        const errText = await response.text().catch(() => '');
        throw new Error(
          `Chat API chat completion stream failed: ${response.status} ${response.statusText} — ${errText}`,
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let finished = false;

      try {
        while (!finished) {
          if (signal?.aborted) break;
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() ?? '';

          for (const frame of frames) {
            const { data } = parseSseFrame(frame);
            if (!data) continue;
            if (data === '[DONE]') {
              finished = true;
              break;
            }
            try {
              const chunk = JSON.parse(data) as OpenAiChatCompletionStreamChunk;
              const { deltaText, reasoningText } = applyOpenAiChatStreamChunk(state, chunk);
              if (deltaText) callbacks.onText?.(deltaText, chunk);
              if (reasoningText) callbacks.onReasoning?.(reasoningText, chunk);
              callbacks.onChunk?.(chunk, state);
            } catch {
              // Drop malformed frames
            }
          }
        }
      } finally {
        try {
          reader.releaseLock();
        } catch {
          // ignore
        }
      }

      const final = finalizeOpenAiChatStream(state);
      callbacks.onDone?.(final, state);
      return final;
    })();

    return { result, state };
  }

  // ── Responses ────────────────────────────────────────────────────────────

  async function responses(
    body: OpenAiResponseRequest,
    signal?: AbortSignal,
  ): Promise<{ raw: OpenAiResponseResult; unified: UnifiedToolResponse }> {
    const requestBody = withDefaultModel({ ...body, stream: false });
    const raw = await chatApiFetchJson<OpenAiResponseResult>(http, {
      path: '/v1/responses',
      body: requestBody,
      signal,
    });
    return { raw, unified: openAiResponsesToUnified(raw) };
  }

  // ── Legacy completions ───────────────────────────────────────────────────

  async function completions(
    body: OpenAiCompletionRequest,
    signal?: AbortSignal,
  ): Promise<OpenAiCompletionResponse> {
    const requestBody = withDefaultModel({ ...body, stream: false });
    return chatApiFetchJson<OpenAiCompletionResponse>(http, {
      path: '/v1/completions',
      body: requestBody,
      signal,
    });
  }

  // ── Embeddings ───────────────────────────────────────────────────────────

  async function embeddings(
    body: OpenAiEmbeddingRequest,
    signal?: AbortSignal,
  ): Promise<OpenAiEmbeddingResponse> {
    const requestBody = withDefaultModel(body);
    return chatApiFetchJson<OpenAiEmbeddingResponse>(http, {
      path: '/v1/embeddings',
      body: requestBody,
      signal,
    });
  }

  return {
    chatCompletion,
    chatCompletionStream,
    responses,
    completions,
    embeddings,
    rawJson: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
      chatApiFetchJson<T>(http, { path, body, signal }),
    raw: (path: string, body?: unknown, signal?: AbortSignal) =>
      chatApiFetch(http, { path, body, signal }),
  };
}
