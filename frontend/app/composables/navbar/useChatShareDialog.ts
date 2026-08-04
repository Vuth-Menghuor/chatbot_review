import { computed, ref, type Ref } from 'vue';
import { useRoute } from '#imports';
import type { NavbarChatShareOption, NavbarShareType } from '~/types/message';
import { usePreferencesStore } from '~/stores/preferences.store';
import { useAuthStore } from '~/stores/auth.store';
import { useChatStore } from '~/stores/chat.store';
import { createChatShare, revokeChatShare } from '~/services/chat-api/chatShare';
import { ChatApiRequestError } from '~/services/chat-api/chatApiHttp';

interface UseNavbarChatShareDialogOptions {
  chatId?: Ref<string | undefined> | string;
}

export const navbarChatShareOptions: NavbarChatShareOption[] = [
  {
    id: 'private',
    title: 'Keep private',
    description: 'Only you have access',
    icon: 'lucide-lock',
  },
  {
    id: 'public',
    title: 'Create public link',
    description: 'Anyone with the link can view',
    icon: 'lucide-globe',
  },
];

export function useNavbarChatShareDialog(options: UseNavbarChatShareDialogOptions = {}) {
  const route = useRoute();
  const runtimeConfig = useRuntimeConfig();
  const preferencesStore = usePreferencesStore();
  const authStore = useAuthStore();
  const chatStore = useChatStore();
  const defaultShareType = computed<NavbarShareType>(() =>
    preferencesStore.publicChatSharing ? 'public' : 'private',
  );
  const shareType = ref<NavbarShareType>(defaultShareType.value);
  const linkCreated = ref(false);
  const isSaving = ref(false);
  const errorMessage = ref('');
  const createdSharePath = ref('');
  const dialogTitle = computed(() => (linkCreated.value ? 'Chat shared' : 'Share chat'));
  const helperText = computed(() => {
    if (!linkCreated.value) return 'Only messages up to this point will be shared.';
    return shareType.value === 'public'
      ? "Future messages aren't included."
      : 'This chat is private again.';
  });
  const primaryActionLabel = computed(() =>
    shareType.value === 'public' ? 'Create share link' : 'Keep private',
  );

  const selectedChatId = computed(() => {
    const optionChatId =
      typeof options.chatId === 'string' ? options.chatId : options.chatId?.value;
    const routeChatId = Array.isArray(route.params.id)
      ? route.params.id[0]
      : route.params.id;
    return optionChatId || (routeChatId as string | undefined) || '';
  });

  const shareLink = computed(() => {
    if (typeof window === 'undefined') return '';
    if (!createdSharePath.value) return '';
    return `${window.location.origin}${createdSharePath.value}`;
  });

  async function persistShareWithToken(token: string, baseUrl: string) {
    if (shareType.value === 'private') {
      await revokeChatShare(baseUrl, token, selectedChatId.value);
      createdSharePath.value = '';
      return;
    }

    const share = await createChatShare(baseUrl, token, selectedChatId.value, {
      visibility: shareType.value,
      client_snapshot: chatStore.getChatMessages(selectedChatId.value),
    });
    createdSharePath.value = share.share_url_path;
  }

  async function updateSharing() {
    if (!selectedChatId.value) {
      errorMessage.value = 'No chat selected to share.';
      return;
    }

    isSaving.value = true;
    errorMessage.value = '';
    try {
      const token = await authStore.getValidAccessToken();
      if (!token) throw new Error('Please sign in again to update sharing.');
      const baseUrl = String(runtimeConfig.public.gdceApiBaseUrl ?? 'http://localhost:8000');

      try {
        await persistShareWithToken(token, baseUrl);
      } catch (error) {
        if (!(error instanceof ChatApiRequestError) || error.status !== 401) throw error;
        const refreshed = await authStore.refreshSession();
        if (!refreshed || !authStore.accessToken) throw error;
        await persistShareWithToken(authStore.accessToken, baseUrl);
      }
      linkCreated.value = true;
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Could not update chat sharing.';
    } finally {
      isSaving.value = false;
    }
  }

  function onClose() {
    linkCreated.value = false;
    shareType.value = defaultShareType.value;
    errorMessage.value = '';
    createdSharePath.value = '';
  }

  return {
    shareType,
    linkCreated,
    isSaving,
    errorMessage,
    dialogTitle,
    helperText,
    primaryActionLabel,
    shareOptions: navbarChatShareOptions,
    shareLink,
    updateSharing,
    onClose,
  };
}
