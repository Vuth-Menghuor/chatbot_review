/**
 * Shared HTTP helper for Chat API services. Centralizes:
 *   - URL joining (so `baseUrl` may or may not include a trailing slash)
 *   - Bearer-token header
 *   - Error normalization into `ChatApiRequestError`
 *
 * Request option types live in `~/types/message`; this module stays fetch-only.
 */

import type { ChatApiFetchOptions, ChatApiHttpConfig } from '~/types/message';

export class ChatApiRequestError extends Error {
  status: number;
  body: string;
  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = 'ChatApiRequestError';
    this.status = status;
    this.body = body;
  }
}

export function buildChatApiUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const trimmedBase = baseUrl.replace(/\/+$/, '');
  const trimmedPath = path.replace(/^\/+/, '');
  return `${trimmedBase}/${trimmedPath}`;
}

export function buildChatApiHeaders(
  config: ChatApiHttpConfig,
  extra?: Record<string, string>,
  accept = 'application/json',
): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: accept,
    ...(extra ?? {}),
  };
  if (config.apiToken) headers.Authorization = `Bearer ${config.apiToken}`;
  return headers;
}

/** Issues a JSON request and returns the parsed JSON body. */
export async function chatApiFetchJson<T>(
  config: ChatApiHttpConfig,
  options: ChatApiFetchOptions,
): Promise<T> {
  const response = await chatApiFetch(config, options);
  return (await response.json()) as T;
}

/**
 * Issues a request and returns the raw `Response`. Useful for streaming
 * (`text/event-stream`) where the caller wants to consume the body manually.
 */
export async function chatApiFetch(
  config: ChatApiHttpConfig,
  options: ChatApiFetchOptions,
): Promise<Response> {
  if (!config.baseUrl) throw new Error('Chat API base URL is not configured');

  const url = buildChatApiUrl(config.baseUrl, options.path);
  const headers = buildChatApiHeaders(config, options.headers, options.accept);
  const method = options.method ?? (options.body ? 'POST' : 'GET');

  const response = await fetch(url, {
    method,
    headers,
    body: options.body == null ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new ChatApiRequestError(
      `Chat API request failed: ${response.status} ${response.statusText} (${url})`,
      response.status,
      text,
    );
  }

  return response;
}
