import { buildChatApiUrl, ChatApiRequestError } from './chatApiHttp';
import { useAuthStore } from '~/stores/auth.store';

export interface GdceStreamOptions {
  baseUrl: string;
  apiToken?: string;
  message: string;
  chatId?: string;
  attachments?: unknown[];
  signal?: AbortSignal;
  onStart?: (data: Record<string, unknown>) => void;
  onToken?: (content: string) => void;
  onMetadata?: (data: Record<string, unknown>) => void;
  onDone?: (data: Record<string, unknown>) => void;
}

export async function getGdceAccessToken(options: GdceStreamOptions): Promise<string> {
  if (options.apiToken) return options.apiToken;

  const authStore = useAuthStore();
  const token = await authStore.getValidAccessToken();
  if (token) return token;

  throw new Error('Not authenticated. Please sign in.');
}

function parseEvent(block: string): { event: string; data: Record<string, unknown> } | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  return { event, data: JSON.parse(dataLines.join('\n')) as Record<string, unknown> };
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
      message: options.message,
      attachments: options.attachments ?? [],
      metadata: { client: 'gdce-nuxt-frontend' },
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

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const handleBlock = (block: string) => {
    const parsed = parseEvent(block);
    if (!parsed) return;
    if (parsed.event === 'start') options.onStart?.(parsed.data);
    else if (parsed.event === 'token') options.onToken?.(String(parsed.data.content ?? ''));
    else if (parsed.event === 'metadata') options.onMetadata?.(parsed.data);
    else if (parsed.event === 'done') options.onDone?.(parsed.data);
    else if (parsed.event === 'error') throw new Error(String(parsed.data.detail ?? 'Chat stream failed'));
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) handleBlock(block);
  }
  buffer += decoder.decode();
  if (buffer.trim()) handleBlock(buffer);
}
