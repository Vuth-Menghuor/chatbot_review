import { useChatStore } from '~/stores/chat.store';
import { storeToRefs } from 'pinia';
import { navigateTo, useRoute } from '#app';
import { tApp } from '~/utils/i18n/tApp';

/**
 * useChatActions provides high-level actions for managing chat lifecycle
 * (creating, deleting, renaming) which interact with the Pinia store.
 */
export const useChatActions = () => {
  const route = useRoute();
  const chatStore = useChatStore();
  const { recentChats, sortedChats, generalChats, activeChatId, isLoadingChats } =
    storeToRefs(chatStore);

  const startNewChat = (title?: string, projectId?: string) => {
    const resolvedTitle = title ?? tApp('chat.newChat', 'New Chat');
    const chat = chatStore.createChat(resolvedTitle, projectId);
    navigateTo(`/chat/${chat.id}`);
    return chat;
  };

  const deleteChat = (id: string) => {
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
