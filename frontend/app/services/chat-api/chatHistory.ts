import { authFetchAuthed } from '~/services/auth-api/authApi';

export interface ServerChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  status?: string | null;
  created_at: string;
}

export interface ServerChatHistory {
  id: string;
  messages: ServerChatMessage[];
}

/** Loads the API-layer's authoritative messages for one chat thread. */
export function getChatHistoryRequest(baseUrl: string, accessToken: string, chatId: string) {
  return authFetchAuthed<ServerChatHistory>(baseUrl, `/api/v1/chats/${chatId}`, accessToken);
}
