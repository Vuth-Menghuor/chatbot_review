import type {
  MenuEntry,
  MenuItem,
  SubmenuItem,
  UseNavbarChatMoreMenuOptions,
} from '~/types/message';
import { computed, ref } from 'vue';
import { navigateTo } from '#imports';
import { LibraryIcon, PinIcon, PinOffIcon, Trash2Icon, UploadIcon } from 'lucide-vue-next';
import { useUiStore } from '~/stores/ui.store';
import { useChatStore } from '~/stores/chat.store';
import { useProjectStore } from '~/stores/project.store';
import { useChatActions } from '~/composables/useChat';
import { useProjects } from '~/composables/useProjects';
import { useNavbarRouteContext } from './useRouteContext';

export function useNavbarChatMoreMenu(options: UseNavbarChatMoreMenuOptions = {}) {
  const uiStore = useUiStore();
  const { route, isChatPage, isProjectPage } = useNavbarRouteContext();
  const chatStore = useChatStore();
  const projectStore = useProjectStore();
  const { togglePin, deleteChat } = useChatActions();
  const { deleteProject } = useProjects();

  const deleteOpen = ref(false);

  const currentItem = computed(() => {
    const id = route.params.id as string;
    if (isProjectPage.value) return projectStore.projects.find((p) => p.id === id);
    if (isChatPage.value) return chatStore.recentChats.find((c) => c.id === id);
    return null;
  });

  const currentItemTitle = computed(() => {
    if (!currentItem.value) return '';
    return 'name' in currentItem.value ? currentItem.value.name : currentItem.value.title;
  });

  const isPinned = computed(() =>
    currentItem.value && 'pinned' in currentItem.value ? !!currentItem.value.pinned : false,
  );

  const onSelect = (item: MenuItem | SubmenuItem) => {
    if (item.value === 'files') {
      uiStore.toggleFilesPanel();
    } else if (item.value === 'pin' || item.value === 'unpin') {
      if (isChatPage.value && route.params.id) {
        togglePin(route.params.id as string);
      }
    } else if (item.value === 'share') {
      options.onShare?.();
    } else if (item.value === 'delete') {
      deleteOpen.value = true;
    }
  };

  async function onDelete() {
    const id = route.params.id as string;
    if (!id) return;

    if (isProjectPage.value) {
      deleteProject(id);
    } else {
      deleteChat(id);
    }

    deleteOpen.value = false;
    if (isProjectPage.value) {
      await navigateTo('/');
    }
  }

  const menuItems = computed<MenuEntry[]>(() => {
    if (!isChatPage.value && !isProjectPage.value) return [];

    const items: MenuEntry[] = [{ label: 'View files in chat', value: 'files', icon: LibraryIcon }];

    if (isChatPage.value) {
      items.push({
        label: isPinned.value ? 'Unpin chat' : 'Pin chat',
        value: isPinned.value ? 'unpin' : 'pin',
        icon: isPinned.value ? PinOffIcon : PinIcon,
      });
      if (uiStore.isMobile) {
        items.push({
          label: 'Share chat',
          value: 'share',
          icon: UploadIcon,
        });
      }
    }

    items.push({ type: 'divider' });
    items.push({ label: 'Delete', value: 'delete', icon: Trash2Icon, danger: true });

    return items;
  });

  return {
    deleteOpen,
    currentItemTitle,
    isProjectPage,
    menuItems,
    onSelect,
    onDelete,
  };
}
