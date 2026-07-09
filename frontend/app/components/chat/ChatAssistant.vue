<script setup lang="ts">
import { computed } from 'vue';
import type { Message } from '~/types/message';
import ChatMessageRenderer from './ChatMessageRenderer.vue';
import ChatAction from '~/components/common/ChatAction.vue';
import FilePreview from '~/components/common/FilePreview.vue';

const props = defineProps<{
  message: Message;
  loading?: boolean;
  currentRenderType?: string;
  thinkingContext?: string;
}>();

const emit = defineEmits<{
  (e: 'regenerate-image', messageId: string): void;
  (e: 'user-reply', payload: { requestId: string; toolName?: string; action: string; values: Record<string, unknown> }): void;
}>();

const showAssistantActions = computed(
  () => props.message.role === 'assistant' && !props.loading && props.message.type !== 'image',
);

const generationDurationLabel = computed(() => {
  if (props.loading || props.message.type === 'image') return '';
  const ms = props.message.generationDurationMs;
  if (ms === undefined || ms === null || Number.isNaN(ms)) return '';
  if (ms < 750) return `Generated in ${Math.round(ms)} ms`;
  const sec = ms / 1000;
  const formatted = sec < 10 ? sec.toFixed(1) : String(Math.round(sec));
  return `Generated in ${formatted.replace(/\.0$/, '')} s`;
});

const handleRegenerateImage = (messageId: string | number) => {
  emit('regenerate-image', String(messageId));
};
</script>

<template>
  <div class="group/assistant flex w-full flex-col font-normal">
    <div class="flex min-w-0 flex-1 flex-col">
      <div class="max-w-full flex-1 overflow-visible rounded-2xl px-4 py-3">
        <p
          v-if="generationDurationLabel"
          class="mb-2 text-md tabular-nums text-gray-500 dark:text-zinc-500"
        >
          {{ generationDurationLabel }}
        </p>

        <ChatMessageRenderer
          :message="message"
          :loading="loading"
          :current-render-type="currentRenderType"
          :thinking-context="thinkingContext"
          @regenerate="handleRegenerateImage"
          @user-reply="(payload) => emit('user-reply', payload)"
        />

        <div v-if="message.files?.length" class="mt-2">
          <FilePreview :files="message.files" readonly />
        </div>

        <div v-if="showAssistantActions" class="mt-3">
          <ChatAction :message="message" @regenerate="handleRegenerateImage" />
        </div>
      </div>
    </div>
  </div>
</template>
