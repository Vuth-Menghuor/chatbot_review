import { onMounted, watch, type Ref } from 'vue';
import type { Message } from '~/types/message';
import { readJson, storageKeys, writeJson } from '~/utils/storage';
import { useChatStore } from '~/stores/chat.store';
import { serializeMessagesForStorage } from '~/utils/file';

function safeWriteChatMessages(chatId: string, value: Message[]) {
  try {
    writeJson(storageKeys.chatMessages(chatId), serializeMessagesForStorage(value));
  } catch {
    // Persisting chat history can fail when storage is full or unavailable.
  }
}

export function useChatPersistence(chatId?: string) {
  const chatStore = useChatStore();
  const initialMessages: Message[] = chatId ? readJson(storageKeys.chatMessages(chatId), []) : [];

  if (chatId) {
    chatStore.hydrateChatIfMessagesExist(chatId);
    chatStore.setActiveChat(chatId);
    chatStore.setChatMessages(chatId, initialMessages);
  }

  function persistMessages(messages: Ref<Message[]>) {
    if (!chatId) return;

    if (import.meta.client) {
      onMounted(() => {
        const stored = readJson<Message[]>(storageKeys.chatMessages(chatId), []);
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
          const existing = readJson<Message[]>(storageKeys.chatMessages(chatId), []);
          if (existing.length > 0) return;
        }
        safeWriteChatMessages(chatId, value);
      },
      { deep: true, immediate: true, flush: 'sync' },
    );
  }

  return { initialMessages, persistMessages };
}
