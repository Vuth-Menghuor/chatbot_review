import { useChatStore } from '~/stores/chat.store';
import { storeToRefs } from 'pinia';
import { navigateTo, useRoute } from '#app';
import { tApp } from '~/utils/i18n/tApp';
import { useAuthStore } from '~/stores/auth.store';
import { useNotificationStore } from '~/stores/notification.store';
import { deleteChatRequest } from '~/services/chat-api';
import { backendUuidOrNull } from '~/utils/id/backendIdentity';

/**
 * useChatActions provides high-level actions for managing chat lifecycle
 * (creating, deleting, renaming) which interact with the Pinia store.
 */
export const useChatActions = () => {
  const route = useRoute();
  const chatStore = useChatStore();
  const authStore = useAuthStore();
  const notificationStore = useNotificationStore();
  const { recentChats, sortedChats, generalChats, activeChatId, isLoadingChats } =
    storeToRefs(chatStore);

  const startNewChat = (title?: string, projectId?: string) => {
    const resolvedTitle = title ?? tApp('chat.newChat', 'New Chat');
    const chat = chatStore.createChat(resolvedTitle, projectId);
    navigateTo(`/chat/${chat.id}`);
    return chat;
  };

  function apiBaseUrl(): string {
    const runtimeConfig = useRuntimeConfig();
    return String(runtimeConfig.public?.gdceApiBaseUrl ?? 'http://localhost:8000').replace(/\/+$/, '');
  }

  const deleteChat = async (id: string): Promise<boolean> => {
    const chat = chatStore.recentChats.find((item) => item.id === id);
    if (!chat) return false;

    const backendChatId = backendUuidOrNull(chat.backendId);
    if (backendChatId) {
      const token = await authStore.getValidAccessToken();
      if (!token) {
        notificationStore.showToast({
          type: 'error',
          title: 'Unable to delete chat',
          message: 'Please sign in and try again.',
        });
        return false;
      }

      try {
        const result = await deleteChatRequest(apiBaseUrl(), token, backendChatId);
        authStore.accessToken = result.accessToken;
      } catch {
        notificationStore.showToast({
          type: 'error',
          title: 'Unable to delete chat',
          message: 'The chat is still saved. Please try again.',
        });
        return false;
      }
    }

    chatStore.deleteChat(id);
    const currentId = route.params.id;
    const pathId =
      typeof currentId === 'string'
        ? currentId
        : Array.isArray(currentId)
          ? currentId[0]
          : undefined;
    if (pathId === id && route.path.startsWith('/chat/')) {
      void navigateTo('/');
    }
    return true;
  };

  const renameChat = (id: string, newTitle: string) => {
    chatStore.renameChat(id, newTitle);
  };

  const togglePin = (id: string) => {
    chatStore.togglePin(id);
  };

  const moveChatToProject = (id: string, projectId?: string) => {
    chatStore.moveChatToProject(id, projectId);
  };

  return {
    recentChats,
    sortedChats,
    generalChats,
    activeChatId,
    isLoadingChats,
    startNewChat,
    deleteChat,
    renameChat,
    togglePin,
    moveChatToProject,
  };
};
