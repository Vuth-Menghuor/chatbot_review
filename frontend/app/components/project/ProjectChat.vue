<script setup lang="ts">
import { computed } from 'vue';
import { PlusIcon } from 'lucide-vue-next';
import type { Chat } from '~/types/message';
import type { MenuItem } from '~/types/ui-menu';
import ChatShareDialog from '~/components/navbar/ChatShareDialog.vue';
import { formatShortDate } from '~/utils/date';
import { useChatContextMenu } from '~/composables/chat/useChatContextMenu';

const props = defineProps<{
  chatList: Chat[];
}>();

const emit = defineEmits<{
  'chat-click': [id: string];
  'new-chat': [];
  'menu-select': [payload: { action: string; chatId: string }];
}>();

const { shareOpen, renameOpen, deleteOpen, activeChat, buildMenuEntries, onRename, onDelete } =
  useChatContextMenu({
    onMenuSelect: (payload) => emit('menu-select', payload),
  });

const chatListEntries = computed<MenuItem[]>(() =>
  props.chatList.map((chat) => ({
    id: chat.id,
    appearance: 'card',
    label: chat.title,
    description: chat.lastMessage || 'No messages yet',
    meta: formatShortDate(chat.createdAt),
    menuItems: buildMenuEntries({
      id: chat.id,
      title: chat.title,
      pinned: chat.pinned,
      projectId: chat.projectId,
    }),
    pinned: !!chat.pinned,
    onClick: () => emit('chat-click', chat.id),
  })),
);
</script>

<template>
  <div class="flex-1 overflow-y-auto custom-scrollbar -mx-2 bg-white px-2 pb-6 dark:bg-zinc-950">
    <BaseMenuList
      v-if="chatListEntries.length"
      tone="nav"
      plain
      full-width
      bg-color="transparent"
      list-class="pa-0 w-full bg-transparent"
      :items="chatListEntries"
    />

    <div v-else class="flex min-h-full flex-col items-center justify-center px-4 py-12 text-center">
      <BaseButton
        variant="text"
        :custom-class="'mb-6 h-20 w-20 rounded-full border-2 border-dashed border-gray-200 dark:border-zinc-600'"
        @click="emit('new-chat')"
      >
        <PlusIcon class="h-10 w-10 text-gray-300 dark:text-zinc-700" />
      </BaseButton>
      <h3 class="mb-2 text-lg font-semibold text-gray-900 dark:text-zinc-100">No chats yet</h3>
      <p class="mx-auto mb-6 max-w-xs text-base text-gray-500 dark:text-zinc-500">
        Start a conversation for this project to begin.
      </p>
    </div>

    <ChatShareDialog v-model="shareOpen" />
    <BaseConfirmDialog
      v-model="renameOpen"
      preset="rename"
      :current-name="activeChat?.title || ''"
      label=" "
      @rename="onRename"
    />
    <BaseConfirmDialog
      v-model="deleteOpen"
      preset="delete"
      :item-name="activeChat?.title || ''"
      item-type="chat"
      @confirm="onDelete"
    />
  </div>
</template>
