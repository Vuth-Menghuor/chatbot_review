import { buildChatApiUrl, ChatApiRequestError } from './chatApiHttp';
import type { Message, NavbarShareType } from '~/types/message';

export interface ChatSharePayload {
  visibility: NavbarShareType;
  client_snapshot: Message[];
}

export interface ChatShareResponse {
  chat_id: string;
  token: string;
  visibility: NavbarShareType;
  title?: string | null;
  share_url_path: string;
  created_at: string;
  updated_at: string;
}

export interface PublicChatShareResponse {
  chat_id: string;
  token: string;
  title?: string | null;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

async function fetchJson<T>(
  baseUrl: string,
  path: string,
  options: { method?: string; token?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  const response = await fetch(buildChatApiUrl(baseUrl, path), {
    method: options.method ?? (options.body ? 'POST' : 'GET'),
    headers,
    body: options.body == null ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ChatApiRequestError(
      `Chat share request failed (${response.status})`,
      response.status,
      body,
    );
  }

  return (await response.json()) as T;
}

export async function createChatShare(
  baseUrl: string,
  token: string,
  chatId: string,
  payload: ChatSharePayload,
): Promise<ChatShareResponse> {
  return fetchJson<ChatShareResponse>(baseUrl, `/api/v1/chats/${chatId}/share`, {
    token,
    body: payload,
  });
}

export async function revokeChatShare(
  baseUrl: string,
  token: string,
  chatId: string,
): Promise<void> {
  await fetchJson(baseUrl, `/api/v1/chats/${chatId}/share`, {
    method: 'DELETE',
    token,
  });
}

export async function getPublicChatShare(
  baseUrl: string,
  shareToken: string,
): Promise<PublicChatShareResponse> {
  return fetchJson<PublicChatShareResponse>(baseUrl, `/api/v1/shared-chats/${shareToken}`);
}
