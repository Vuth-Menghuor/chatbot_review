import { ref } from 'vue';
import {
  FolderOpenIcon,
  PencilIcon,
  PinIcon,
  PinOffIcon,
  ShareIcon,
  Trash2Icon,
} from 'lucide-vue-next';
import { useChatActions } from '~/composables/useChat';
import { useProjects } from '~/composables/useProjects';
import type { MenuEntry } from '~/types/ui-menu';

export interface ChatContextTarget {
  id: string;
  title: string;
  pinned?: boolean;
  projectId?: string;
}

export interface UseChatContextMenuOptions {
  includeMoveToProject?: boolean;
  onMenuSelect?: (payload: { action: string; chatId: string; projectId?: string }) => void;
}

export function useChatContextMenu(options: UseChatContextMenuOptions = {}) {
  const shareOpen = ref(false);
  const renameOpen = ref(false);
  const deleteOpen = ref(false);
  const activeChat = ref<ChatContextTarget | null>(null);

  const { renameChat, deleteChat, togglePin, moveChatToProject } = useChatActions();
  const { projects } = useProjects();
  const { t } = useI18n();

  function setActiveChat(chat: ChatContextTarget) {
    activeChat.value = chat;
  }

  function moveChat(chat: ChatContextTarget, projectId?: string) {
    const isGeneral = !projectId;
    if (isGeneral && !chat.projectId) return;
    if (!isGeneral && chat.projectId === projectId) return;

    moveChatToProject(chat.id, projectId);
    options.onMenuSelect?.({ action: 'move', chatId: chat.id, projectId });
  }

  function buildMoveToProjectChildren(chat: ChatContextTarget): MenuEntry[] {
    const children: MenuEntry[] = [
      {
        label: t('sidebar.chatMenu.generalChat'),
        disabled: !chat.projectId,
        onClick: () => moveChat(chat),
      },
    ];

    if (projects.value.length) {
      children.push({ type: 'divider' });
      for (const project of projects.value) {
        children.push({
          label: project.name,
          disabled: chat.projectId === project.id,
          onClick: () => moveChat(chat, project.id),
        });
      }
    }

    return children;
  }

  function handleAction(action: string, chat: ChatContextTarget) {
    setActiveChat(chat);
    if (action === 'share') {
      shareOpen.value = true;
    } else if (action === 'rename') {
      renameOpen.value = true;
    } else if (action === 'delete') {
      deleteOpen.value = true;
    } else if (action === 'pin' || action === 'unpin') {
      togglePin(chat.id);
    }
    options.onMenuSelect?.({ action, chatId: chat.id });
  }

  function buildMenuEntries(chat: ChatContextTarget): MenuEntry[] {
    const pinned = !!chat.pinned;
    const entries: MenuEntry[] = [
      {
        label: t('common.share'),
        icon: ShareIcon,
        onClick: () => handleAction('share', chat),
      },
      {
        label: t('common.rename'),
        icon: PencilIcon,
        onClick: () => handleAction('rename', chat),
      },
    ];

    if (options.includeMoveToProject !== false) {
      entries.push({
        type: 'submenu',
        label: t('sidebar.chatMenu.moveToProject'),
        icon: FolderOpenIcon,
        children: buildMoveToProjectChildren(chat),
      });
    }

    entries.push(
      {
        label: pinned ? t('sidebar.chatMenu.unpin') : t('sidebar.chatMenu.pin'),
        icon: pinned ? PinOffIcon : PinIcon,
        onClick: () => handleAction(pinned ? 'unpin' : 'pin', chat),
      },
      { type: 'divider' },
      {
        label: t('common.delete'),
        icon: Trash2Icon,
        danger: true,
        onClick: () => handleAction('delete', chat),
      },
    );

    return entries;
  }

  function onRename(newName: string) {
    if (!activeChat.value) return;
    renameChat(activeChat.value.id, newName);
    renameOpen.value = false;
  }

  function onDelete() {
    if (!activeChat.value) return;
    deleteChat(activeChat.value.id);
    deleteOpen.value = false;
  }

  return {
    shareOpen,
    renameOpen,
    deleteOpen,
    activeChat,
    buildMenuEntries,
    onRename,
    onDelete,
  };
}
