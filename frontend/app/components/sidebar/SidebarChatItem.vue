<template>
  <BaseMenuListItem
    tone="nav"
    :label="title"
    :tooltip="title"
    :rail="rail"
    :active="isActive"
    :menu-items="menuEntries"
    :pinned="pinned"
    @click="onChatClick"
    @menu-select="onMenuSelect"
  />

  <ChatShareDialog v-model="shareOpen" />
  <BaseConfirmDialog
    v-model="renameOpen"
    preset="rename"
    :current-name="title"
    label=" "
    @rename="onRename"
  />
  <BaseConfirmDialog
    v-model="deleteOpen"
    preset="delete"
    :item-name="title"
    item-type="chat"
    @confirm="onDelete"
  />
</template>

<script setup lang="ts">
import { useUiStore } from '~/stores/ui.store';
import { useRoute } from 'vue-router';
import { computed, nextTick } from 'vue';
import { navigateTo } from '#imports';
import type { MenuItem, SubmenuItem } from '~/types/ui-menu';
import ChatShareDialog from '~/components/navbar/ChatShareDialog.vue';
import { useChatContextMenu } from '~/composables/chat/useChatContextMenu';

interface Props {
  chatId: string;
  title: string;
  pinned?: boolean;
  projectId?: string;
  rail?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  pinned: false,
  rail: false,
});

const emit = defineEmits<{
  menu: [item: MenuItem | SubmenuItem];
  'menu-select': [payload: { action: string; chatId: string }];
}>();

const uiStore = useUiStore();
const route = useRoute();

const chatTarget = computed(() => ({
  id: props.chatId,
  title: props.title,
  pinned: props.pinned,
  projectId: props.projectId,
}));

const { shareOpen, renameOpen, deleteOpen, buildMenuEntries, onRename, onDelete } =
  useChatContextMenu({
    onMenuSelect: (payload) => emit('menu-select', payload),
  });

const menuEntries = computed(() => buildMenuEntries(chatTarget.value));

const isActive = computed(() => route.path.includes(`/chat/${props.chatId}`));

function onChatClick() {
  uiStore.closeMobileSidebar();
  navigateTo(`/chat/${props.chatId}`);
  nextTick(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

function onMenuSelect(item: MenuItem | SubmenuItem) {
  emit('menu', item);
}
</script>
