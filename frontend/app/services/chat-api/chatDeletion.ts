import { authFetchAuthed } from '~/services/auth-api/authApi';

export interface DeleteChatResponse {
  message: string;
}

/** Deletes the server-side record for a chat the current user owns. */
export function deleteChatRequest(baseUrl: string, accessToken: string, chatId: string) {
  return authFetchAuthed<DeleteChatResponse>(
    baseUrl,
    `/api/v1/chats/${chatId}`,
    accessToken,
    { method: 'DELETE' },
  );
}
