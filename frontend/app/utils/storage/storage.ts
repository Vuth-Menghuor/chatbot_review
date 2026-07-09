export const storageKeys = {
  chatHistory: 'chat_history',
  chatMessagesPrefix: 'chat_messages_',
  projectList: 'project_list',
  railMode: 'railMode',
  sidebarWidth: 'sidebarWidth',
  appTheme: 'appTheme',
  responseCompletionToast: 'responseCompletionToast',
  notificationPreferences: 'notificationPreferences',
  chatPreferences: 'chatPreferences',
  uiPreferences: 'uiPreferences',
  privacyPreferences: 'privacyPreferences',
  chatMessages: (chatId: string) => `${storageKeys.chatMessagesPrefix}${chatId}`,
} as const;

export function readJson<T>(key: string, fallback: T): T {
  if (!import.meta.client) return fallback;
  try {
    const value = localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJson<T>(key: string, value: T): void {
  if (!import.meta.client) return;
  localStorage.setItem(key, JSON.stringify(value));
}

export function readString(key: string): string | null {
  if (!import.meta.client) return null;
  return localStorage.getItem(key);
}

export function writeString(key: string, value: string): void {
  if (!import.meta.client) return;
  localStorage.setItem(key, value);
}

export function removeKey(key: string): void {
  if (!import.meta.client) return;
  localStorage.removeItem(key);
}

export function removeChatMessageKeys(chatIds?: string[]): void {
  if (!import.meta.client) return;

  if (chatIds?.length) {
    chatIds.forEach((chatId) => removeKey(storageKeys.chatMessages(chatId)));
    return;
  }

  Object.keys(localStorage)
    .filter((key) => key.startsWith(storageKeys.chatMessagesPrefix))
    .forEach((key) => localStorage.removeItem(key));
}
