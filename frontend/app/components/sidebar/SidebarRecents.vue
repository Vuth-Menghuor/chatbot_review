<template>
  <div>
    <div v-if="!rail">
      <div class="mb-2 flex items-center justify-between rounded px-3 py-1">
        <span
          class="text-sm font-bold uppercase tracking-normal font-sans text-medium-emphasis dark:text-zinc-400"
        >
          {{ $t('sidebar.recents') }}
        </span>
      </div>

      <BaseMenuList tone="nav" bg-color="transparent" list-class="pa-0">
        <div v-if="isLoadingChats" class="space-y-1 px-1 py-1">
          <div v-for="row in skeletonRows" :key="row" class="flex h-9 items-center rounded-lg px-3">
            <div
              class="h-4 animate-pulse rounded bg-gray-200 dark:bg-zinc-800"
              :class="row % 3 === 0 ? 'w-4/5' : row % 2 === 0 ? 'w-2/3' : 'w-11/12'"
            />
          </div>
        </div>

        <SidebarChatItem
          v-for="chat in generalChats"
          :key="chat.id"
          :chat-id="chat.id"
          :title="chat.title"
          :pinned="chat.pinned"
          :project-id="chat.projectId"
          @menu="onMenu"
        />
      </BaseMenuList>
    </div>

    <BaseRailPanel
      v-else
      :icon="MessageCircleMoreIcon"
      :tooltip="$t('sidebar.recentChats')"
      :title="$t('sidebar.recents')"
      :width="200"
    >
      <div v-if="isLoadingChats" class="space-y-1 px-1 py-1">
        <div v-for="row in skeletonRows" :key="row" class="flex h-9 items-center rounded-lg px-3">
          <div
            class="h-4 animate-pulse rounded bg-gray-200 dark:bg-zinc-800"
            :class="row % 3 === 0 ? 'w-4/5' : row % 2 === 0 ? 'w-2/3' : 'w-11/12'"
          />
        </div>
      </div>

      <SidebarChatItem
        v-for="chat in generalChats"
        :key="chat.id"
        :chat-id="chat.id"
        :title="chat.title"
        :pinned="chat.pinned"
        :project-id="chat.projectId"
        @menu="onMenu"
      />
    </BaseRailPanel>
  </div>
</template>

<script setup lang="ts">
import { MessageCircleMoreIcon } from 'lucide-vue-next';
import type { MenuItem, SubmenuItem } from '~/types/ui-menu';
import { useChatActions } from '~/composables/useChat';

interface Props {
  rail?: boolean;
}
withDefaults(defineProps<Props>(), {
  rail: false,
});

const emit = defineEmits<{
  (e: 'menu', item: MenuItem | SubmenuItem): void;
}>();

const { generalChats, isLoadingChats } = useChatActions();
const skeletonRows = [1, 2, 3, 4, 5, 6];

function onMenu(item: MenuItem | SubmenuItem) {
  emit('menu', item);
}
</script>
