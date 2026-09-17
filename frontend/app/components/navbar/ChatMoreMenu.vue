<template>
  <BaseMenu :items="menuItems" location="bottom end" :offset="5" width="220" @select="onSelect">
    <template #activator="{ props }">
      <BaseIconButton
        v-bind="props"
        :icon="MoreHorizontalIcon"
        width="36"
        height="36"
        custom-class="text-gray-700 hover:!bg-gray-200/50 hover:!text-gray-800 dark:text-zinc-200 dark:hover:!bg-zinc-800 dark:hover:!text-zinc-100"
        :tooltip="$t('chat.moreOptions')"
      />
    </template>

    <template #default>
      <BaseConfirmDialog
        v-model="deleteOpen"
        preset="delete"
        :item-name="currentItemTitle"
        :item-type="isProjectPage ? 'project' : 'chat'"
        @confirm="onDelete"
      />
    </template>
  </BaseMenu>
</template>

<script setup lang="ts">
import { MoreHorizontalIcon } from 'lucide-vue-next';
import { useNavbarChatMoreMenu } from '~/composables/navbar/useChatMoreMenu';

const emit = defineEmits<{
  (e: 'share'): void;
}>();

const { deleteOpen, currentItemTitle, isProjectPage, menuItems, onSelect, onDelete } =
  useNavbarChatMoreMenu({ onShare: () => emit('share') });
</script>
