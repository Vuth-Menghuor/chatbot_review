import { computed } from 'vue';
import { useRoute } from '#imports';
import { useChatStore } from '~/stores/chat.store';
import type { ChatPanelFile, Message } from '~/types/message';
import { toChatPanelFile } from '~/utils/file';

export function useChatFiles() {
  const route = useRoute();
  const chatStore = useChatStore();
  const activeChatId = computed(() => {
    if (!route.path.includes('/chat/')) return null;
    const id = route.params.id;
    return typeof id === 'string' ? id : null;
  });

  const messages = computed<Message[]>(() => {
    if (!activeChatId.value) return [];

    const storeMessages = chatStore.getChatMessages(activeChatId.value);
    if (storeMessages.length) return storeMessages;

    // Message hydration applies the cache expiry and size policy before placing
    // data in the store, so do not bypass it with a direct Local Storage read.
    return [];
  });

  const files = computed(() =>
    messages.value.flatMap((message) =>
      (message.files ?? [])
        .map((file, index) => toChatPanelFile(file, message, index))
        .filter((file): file is ChatPanelFile => Boolean(file)),
    ),
  );

  return {
    activeChatId,
    files,
  };
}
