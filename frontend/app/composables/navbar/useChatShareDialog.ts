import { computed, ref } from 'vue';
import { useRoute } from '#imports';
import type { NavbarChatShareOption, NavbarShareType } from '~/types/message';

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

export function useNavbarChatShareDialog() {
  const route = useRoute();
  const shareType = ref<NavbarShareType>('private');
  const linkCreated = ref(false);

  const shareLink = computed(() => {
    if (typeof window === 'undefined') return '';
    const chatId = (route.params.id as string) ?? '';
    return `${window.location.origin}/share/${chatId}`;
  });

  function createLink() {
    linkCreated.value = true;
  }

  function onClose() {
    linkCreated.value = false;
    shareType.value = 'private';
  }

  return {
    shareType,
    linkCreated,
    shareOptions: navbarChatShareOptions,
    shareLink,
    createLink,
    onClose,
  };
}
