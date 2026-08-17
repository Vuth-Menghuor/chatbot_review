import { buildChatApiUrl, ChatApiRequestError } from './chatApiHttp';
import { useAuthStore } from '~/stores/auth.store';
import { readSseStream } from '~/utils/stream';

export interface GdceStreamOptions {
  baseUrl: string;
  apiToken?: string;
  message: string;
  chatId?: string;
  projectId?: string;
  attachments?: unknown[];
  presentation?: GdcePresentationPreference;
  context?: Record<string, unknown>;
  signal?: AbortSignal;
  onStart?: (data: Record<string, unknown>) => void;
  onProgress?: (data: Record<string, unknown>) => void;
  onDelta?: (content: string) => void | Promise<void>;
  onDone?: (data: Record<string, unknown>) => void;
  onError?: (data: Record<string, unknown>) => void;
}

export interface GdcePresentationPreference {
  preferred_blocks: string[];
  chart_type?: 'pie' | 'donut' | 'bar' | 'line' | 'area';
  fallback: 'markdown';
}

export interface GdceSendOptions {
  baseUrl: string;
  apiToken?: string;
  message: string;
  chatId?: string;
  projectId?: string;
  attachments?: unknown[];
  presentation?: GdcePresentationPreference;
  context?: Record<string, unknown>;
  signal?: AbortSignal;
}

export class ChatStreamEventError extends Error {
  constructor(public readonly detail: string) {
    super(detail);
    this.name = 'ChatStreamEventError';
  }
}

export async function getGdceAccessToken(options: GdceStreamOptions): Promise<string> {
  if (options.apiToken) return options.apiToken;

  const authStore = useAuthStore();
  const token = await authStore.getValidAccessToken();
  if (token) return token;

  throw new Error('Not authenticated. Please sign in.');
}

export async function streamGdceChat(options: GdceStreamOptions): Promise<void> {
  let token = await getGdceAccessToken(options);
  const requestStream = () => fetch(buildChatApiUrl(options.baseUrl, '/api/v1/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      chat_id: options.chatId || null,
      project_id: options.projectId || null,
      message: options.message,
      attachments: options.attachments ?? [],
      metadata: { client: 'gdce-nuxt-frontend' },
      ...(options.presentation ? { presentation: options.presentation } : {}),
      ...(options.context ? { context: options.context } : {}),
    }),
    signal: options.signal,
  });

  let response = await requestStream();
  if (response.status === 401 && !options.apiToken) {
    const authStore = useAuthStore();
    const refreshed = await authStore.refreshSession();
    if (refreshed && authStore.accessToken) {
      token = authStore.accessToken;
      response = await requestStream();
    }
  }

  if (!response.ok || !response.body) {
    const body = await response.text();
    throw new ChatApiRequestError(`Chat request failed (${response.status})`, response.status, body);
  }

  await readSseStream(response.body, async ({ event, json }) => {
    if (!isRecord(json)) return;
    if (event === 'start') options.onStart?.(json);
    else if (event === 'progress') options.onProgress?.(json);
    else if (event === 'delta') await options.onDelta?.(String(json.content ?? ''));
    else if (event === 'done') options.onDone?.(json);
    else if (event === 'error') {
      options.onError?.(json);
      throw new ChatStreamEventError(String(json.detail ?? 'Chat stream failed'));
    }
  }, { signal: options.signal });
}

/**
 * Fetches the authoritative normalized response for UI-side progressive
 * rendering when an upstream stream is known to provide a different narrative.
 */
export async function sendGdceChat(options: GdceSendOptions): Promise<Record<string, unknown>> {
  let token = await getGdceAccessToken(options);
  const request = () => fetch(buildChatApiUrl(options.baseUrl, '/api/v1/chat/send'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      chat_id: options.chatId || null,
      project_id: options.projectId || null,
      message: options.message,
      attachments: options.attachments ?? [],
      metadata: { client: 'gdce-nuxt-frontend', presentation: 'progressive' },
      ...(options.presentation ? { presentation: options.presentation } : {}),
      ...(options.context ? { context: options.context } : {}),
    }),
    signal: options.signal,
  });

  let response = await request();
  if (response.status === 401 && !options.apiToken) {
    const authStore = useAuthStore();
    const refreshed = await authStore.refreshSession();
    if (refreshed && authStore.accessToken) {
      token = authStore.accessToken;
      response = await request();
    }
  }

  if (!response.ok) {
    const body = await response.text();
    throw new ChatApiRequestError(`Chat request failed (${response.status})`, response.status, body);
  }

  const data: unknown = await response.json();
  if (!isRecord(data)) throw new ChatApiRequestError('Chat request returned an invalid response', response.status, '');
  return data;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}
