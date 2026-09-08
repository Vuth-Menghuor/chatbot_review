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
  questionCount?: number;
}>();

const emit = defineEmits<{
  (e: 'like', messageId: string): void;
  (e: 'dislike', messageId: string): void;
  (e: 'regenerate-image', messageId: string): void;
  (
    e: 'user-reply',
    payload: {
      requestId: string;
      toolName?: string;
      action: string;
      values: Record<string, unknown>;
    },
  ): void;
}>();

function handleLike(messageId: string | number) {
  emit('like', String(messageId));
}

function handleDislike(messageId: string | number) {
  emit('dislike', String(messageId));
}

const showAssistantActions = computed(
  () => props.message.role === 'assistant' && !props.loading && props.message.type !== 'image',
);

const isResponseInProgress = computed(() =>
  Boolean(
    props.loading ||
    props.message.status === 'thinking' ||
    props.message.status === 'streaming' ||
    props.message.responseStatus === 'processing' ||
    props.message.responseStatus === 'pending',
  ),
);

const thinkingSteps = computed(() => [
  ...new Set(props.message.progressSteps?.filter((step) => step.trim()) ?? []),
]);

const thinkingCount = computed(() => props.questionCount ?? thinkingSteps.value.length);

const thinkingDurationLabel = computed(() => {
  const ms = props.message.generationDurationMs;
  if (!ms || ms < 1) return '';
  return `${Math.max(1, Math.round(ms / 1000))} seconds`;
});

const coverageBadge = computed(() => {
  if (props.loading || props.message.type === 'image' || props.message.coverage !== 'partial') {
    return null;
  }
  return {
    label: 'Limited source coverage',
    title:
      'The retrieved documents contain related information but not a complete answer for every requested detail.',
  };
});

const handleRegenerateImage = (messageId: string | number) => {
  emit('regenerate-image', String(messageId));
};
</script>

<template>
  <div class="group/assistant flex w-full flex-col font-normal">
    <div class="flex min-w-0 flex-1 flex-col">
      <div
        class="flex max-w-full flex-1 items-start gap-3 overflow-visible rounded-2xl px-3 py-3 sm:px-4"
      >
        <div class="relative mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center">
          <span
            v-if="isResponseInProgress"
            class="absolute inset-0 rounded-full border-2 border-blue-500/80 border-l-transparent motion-safe:animate-spin"
            aria-hidden="true"
          />
          <img
            class="h-8 w-8 rounded-full object-contain"
            src="/logo/3d-ai-avatar-transparent.png"
            alt="Customs AI Avatar"
            draggable="false"
          />
        </div>

        <div class="min-w-0 flex-1">
          <div
            v-if="coverageBadge"
            class="mb-2 flex flex-wrap items-center gap-2 text-md text-gray-500 dark:text-zinc-500"
          >
            <span
              v-if="coverageBadge"
              class="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200"
              :title="coverageBadge.title"
            >
              {{ coverageBadge.label }}
            </span>
          </div>

          <details
            v-if="thinkingSteps.length"
            class="mb-3 text-sm text-slate-500 dark:text-zinc-400"
            :open="isResponseInProgress"
          >
            <summary class="cursor-pointer select-none list-none">
              <span class="inline-flex items-center gap-1">
                <span aria-hidden="true">⌄</span>
                <span>{{ $t('reasoning.progress', { count: thinkingCount }) }}</span>
                <span v-if="thinkingDurationLabel">· {{ thinkingDurationLabel }}</span>
              </span>
            </summary>
            <ol class="mt-2 space-y-1 border-l border-slate-300 pl-3 text-xs dark:border-zinc-700">
              <li v-for="step in thinkingSteps" :key="step">{{ step }}</li>
            </ol>
          </details>

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

          <div v-if="showAssistantActions">
            <ChatAction
              :message="message"
              @like="handleLike"
              @dislike="handleDislike"
              @regenerate="handleRegenerateImage"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
