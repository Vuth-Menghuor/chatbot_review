<script setup lang="ts">
import type { Message } from '~/types/message';
import { useChatAction } from '~/composables/common/useChatAction';

const props = defineProps<{
  message: Message;
}>();

const emit = defineEmits<{
  (e: 'copy', content: string): void;
  (e: 'like', messageId: string | number): void;
  (e: 'dislike', messageId: string | number): void;
  (e: 'regenerate', messageId: string | number): void;
  (e: 'edit', messageId: string | number): void;
}>();

const { t } = useI18n();
const { actions, handleAction, getButtonClass } = useChatAction(props, emit);
</script>

<template>
  <div class="mt-1 flex flex-wrap items-center gap-0.5">
    <template v-for="item in actions" :key="item.action">
      <BaseButton
        v-if="item.action === 'sources'"
        variant="text"
        size="small"
        :prepend-icon="item.icon"
        :custom-class="[
          'h-8 shrink-0 rounded-lg px-2 text-xs font-semibold normal-case tracking-normal',
          'text-neutral-500 hover:text-neutral-700 hover:bg-neutral-100/70 dark:text-neutral-400 dark:hover:text-neutral-300 dark:hover:bg-neutral-800/60',
        ].join(' ')"
        :tooltip="item.tooltip"
        @click="handleAction(item.action)"
      >
        {{ t('chat.filesPanel.sources') }}
        <span
          class="ml-1.5 rounded bg-neutral-200/70 px-1.5 py-0.5 font-mono text-[10px] font-bold text-neutral-500 dark:bg-neutral-700/60 dark:text-neutral-400"
        >
          {{ message.sources?.length }}
        </span>
      </BaseButton>

      <BaseIconButton
        v-else
        :icon="item.icon"
        size="small"
        :tooltip="item.tooltip"
        variant="text"
        color="neutral"
        :custom-class="getButtonClass(item.action)"
        @click="handleAction(item.action)"
      />
    </template>
  </div>
</template>
