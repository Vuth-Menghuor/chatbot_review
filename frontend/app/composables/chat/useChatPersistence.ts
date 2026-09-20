import { onMounted, watch, type Ref } from 'vue';
import type { Message } from '~/types/message';
import { readJson, removeKey, storageKeys, writeJson } from '~/utils/storage';
import { useChatStore } from '~/stores/chat.store';
import { serializeMessagesForStorage } from '~/utils/file';

const CHAT_MESSAGE_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_CACHED_MESSAGES_PER_CHAT = 100;

function readCachedMessages(chatId: string): Message[] {
  const messages = readJson<Message[]>(storageKeys.chatMessages(chatId), []);
  const newestTimestamp = Math.max(...messages.map((message) => Date.parse(message.createdAt ?? '')), Number.NaN);
  if (messages.length && (!Number.isFinite(newestTimestamp) || Date.now() - newestTimestamp > CHAT_MESSAGE_CACHE_TTL_MS)) {
    removeKey(storageKeys.chatMessages(chatId));
    return [];
  }
  return messages.slice(-MAX_CACHED_MESSAGES_PER_CHAT);
}

function safeWriteChatMessages(chatId: string, value: Message[]) {
  try {
    writeJson(
      storageKeys.chatMessages(chatId),
      serializeMessagesForStorage(value.slice(-MAX_CACHED_MESSAGES_PER_CHAT)),
    );
  } catch {
    // Persisting chat history can fail when storage is full or unavailable.
  }
}

export function useChatPersistence(chatId?: string) {
  const chatStore = useChatStore();
  const initialMessages: Message[] = chatId ? readCachedMessages(chatId) : [];

  if (chatId) {
    chatStore.hydrateChatIfMessagesExist(chatId);
    chatStore.setActiveChat(chatId);
    chatStore.setChatMessages(chatId, initialMessages);
  }

  function persistMessages(messages: Ref<Message[]>) {
    if (!chatId) return;

    if (import.meta.client) {
      onMounted(() => {
        const stored = readCachedMessages(chatId);
        if (stored.length > 0 && messages.value.length === 0) {
          messages.value = stored;
          chatStore.setChatMessages(chatId, stored);
        }
      });
    }

    watch(
      messages,
      (value) => {
        chatStore.setChatMessages(chatId, value);
        if (value.length === 0) {
          const existing = readCachedMessages(chatId);
          if (existing.length > 0) return;
        }
        safeWriteChatMessages(chatId, value);
      },
      { deep: true, immediate: true, flush: 'sync' },
    );
  }

  return { initialMessages, persistMessages };
}
