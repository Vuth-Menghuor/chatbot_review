import { defineStore } from 'pinia';
import { ref, watch, computed } from 'vue';
import { parseISO, isValid } from 'date-fns';
import {
  readJson,
  removeChatMessageKeys,
  removeKey,
  storageKeys,
  writeJson,
} from '~/utils/storage';
import { tApp } from '~/utils/i18n/tApp';
import type { Chat, Message } from '~/types/message';

export const useChatStore = defineStore('chat', () => {
  const recentChats = ref<Chat[]>([]);
  const activeChatId = ref<string | null>(null);
  const messagesByChatId = ref<Record<string, Message[]>>({});
  const isLoaded = ref(false);
  const isLoadingChats = ref(false);
  if (import.meta.client) {
    isLoadingChats.value = true;
    queueMicrotask(() => {
      loadChatHistory();
    });
  }

  // Persist changes
  watch(
    recentChats,
    (val) => {
      if (isLoaded.value) {
        writeJson(storageKeys.chatHistory, val);
      }
    },
    { deep: true, flush: 'sync' },
  );

  function chatSortTime(iso: string) {
    const d = parseISO(iso);
    return isValid(d) ? d.getTime() : 0;
  }

  const sortedChats = computed(() => {
    return [...recentChats.value].sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return chatSortTime(b.createdAt) - chatSortTime(a.createdAt);
    });
  });

  const generalChats = computed(() => {
    return sortedChats.value.filter((c) => !c.projectId);
  });

  function loadChatHistory() {
    if (!import.meta.client || isLoaded.value) return;

    try {
      const storedChats = readJson<Chat[]>(storageKeys.chatHistory, []);
      const draftChats = recentChats.value.filter(
        (chat) => !storedChats.some((stored) => stored.id === chat.id),
      );
      recentChats.value = [...draftChats, ...storedChats];
    } finally {
      isLoaded.value = true;
      isLoadingChats.value = false;
    }
  }

  function createChat(title: string, projectId?: string) {
    const id =
      typeof globalThis.crypto?.randomUUID === 'function'
        ? globalThis.crypto.randomUUID()
        : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = (Math.random() * 16) | 0;
            const v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
          });
    const newChat: Chat = {
      id,
      title,
      projectId,
      createdAt: new Date().toISOString(),
    };
    recentChats.value.unshift(newChat);
    // Persist immediately to avoid losing just-created chats on fast navigation/reload.
    if (isLoaded.value) {
      writeJson(storageKeys.chatHistory, recentChats.value);
    }
    activeChatId.value = id;
    return newChat;
  }

  function setBackendChatId(localChatId: string, backendChatId: string) {
    const chat = recentChats.value.find((item) => item.id === localChatId);
    if (!chat) return;
    chat.backendId = backendChatId;
    if (isLoaded.value) {
      writeJson(storageKeys.chatHistory, recentChats.value);
    }
  }

  function setBackendProjectId(localChatId: string, backendProjectId: string) {
    const chat = recentChats.value.find((item) => item.id === localChatId);
    if (!chat) return;
    chat.backendProjectId = backendProjectId;
    if (isLoaded.value) {
      writeJson(storageKeys.chatHistory, recentChats.value);
    }
  }

  function deriveChatTitleFromMessages(messages: Message[]) {
    const firstUserMessage = messages.find((message) => message.role === 'user');
    const candidate = firstUserMessage?.content?.trim() ?? '';
    if (!candidate) return tApp('chat.newChat', 'New Chat');
    return candidate.length > 60 ? `${candidate.slice(0, 60)}...` : candidate;
  }

  function hydrateChatIfMessagesExist(chatId: string) {
    const existingChat = recentChats.value.find((chat) => chat.id === chatId);
    if (existingChat) {
      activeChatId.value = chatId;
      return true;
    }

    const storedMessages = readJson<Message[]>(storageKeys.chatMessages(chatId), []);
    if (!storedMessages.length) return false;

    const hydratedChat: Chat = {
      id: chatId,
      title: deriveChatTitleFromMessages(storedMessages),
      createdAt: storedMessages[0]?.createdAt ?? new Date().toISOString(),
      lastMessage: storedMessages[storedMessages.length - 1]?.content,
    };

    recentChats.value.unshift(hydratedChat);
    messagesByChatId.value[chatId] = storedMessages;
    activeChatId.value = chatId;
    return true;
  }

  function deleteChat(id: string) {
    recentChats.value = recentChats.value.filter((c) => c.id !== id);
    if (activeChatId.value === id) {
      activeChatId.value = null;
    }
    if (id in messagesByChatId.value) {
      const next = { ...messagesByChatId.value };
      const { [id]: deleted, ...rest } = next;
      messagesByChatId.value = rest;
    }
    removeChatMessageKeys([id]);
  }

  function renameChat(id: string, newTitle: string) {
    const chat = recentChats.value.find((c) => c.id === id);
    if (chat) {
      chat.title = newTitle;
    }
  }

  function togglePin(id: string) {
    const chat = recentChats.value.find((c) => c.id === id);
    if (chat) {
      chat.pinned = !chat.pinned;
    }
  }

  function moveChatToProject(id: string, projectId?: string) {
    const chat = recentChats.value.find((c) => c.id === id);
    if (!chat) return;

    if (projectId) {
      chat.projectId = projectId;
    } else {
      delete chat.projectId;
    }
  }

  function clearAll() {
    recentChats.value = [];
    messagesByChatId.value = {};
    removeKey(storageKeys.chatHistory);
    removeChatMessageKeys();
  }

  function setActiveChat(id: string | null) {
    activeChatId.value = id;
  }

  function setChatMessages(chatId: string, messages: Message[]) {
    messagesByChatId.value[chatId] = messages;
    const chat = recentChats.value.find((c) => c.id === chatId);
    if (!chat) return;

    const latestMessage = [...messages].reverse().find((message) => message.content?.trim());
    chat.lastMessage = latestMessage?.content;
  }

  function getChatMessages(chatId?: string | null) {
    if (!chatId) return [];
    return messagesByChatId.value[chatId] ?? [];
  }

  return {
    recentChats,
    sortedChats,
    generalChats,
    activeChatId,
    messagesByChatId,
    isLoaded,
    isLoadingChats,
    loadChatHistory,
    createChat,
    setBackendChatId,
    setBackendProjectId,
    deleteChat,
    renameChat,
    togglePin,
    moveChatToProject,
    clearAll,
    setActiveChat,
    setChatMessages,
    getChatMessages,
    hydrateChatIfMessagesExist,
  };
});
