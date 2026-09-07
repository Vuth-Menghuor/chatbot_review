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

const generationDurationLabel = computed(() => {
  if (props.loading || props.message.type === 'image') return '';
  const ms = props.message.generationDurationMs;
  if (ms === undefined || ms === null || Number.isNaN(ms)) return '';
  if (ms < 750) return `Generated in ${Math.round(ms)} ms`;
  const sec = ms / 1000;
  const formatted = sec < 10 ? sec.toFixed(1) : String(Math.round(sec));
  return `Generated in ${formatted.replace(/\.0$/, '')} s`;
});

const responseStateLabel = computed(() => {
  if (props.message.type === 'image') return '';
  const mode = props.message.responseMode;
  const status = props.message.responseStatus;
  if (!mode && !status && !props.message.progressMessage) return '';
  const modeLabel = mode ? mode.charAt(0).toUpperCase() + mode.slice(1) : 'Response';
  const statusLabel = status ? status.replace(/_/g, ' ') : 'processing';
  if (props.loading) return `${modeLabel} · ${statusLabel}`;
  if (status && status !== 'completed') return `${modeLabel} · ${statusLabel}`;
  return '';
});

const isResponseInProgress = computed(() =>
  Boolean(
    props.loading ||
      props.message.status === 'thinking' ||
      props.message.status === 'streaming' ||
      props.message.responseStatus === 'processing' ||
      props.message.responseStatus === 'pending',
  ),
);

const responseAvatarLabel = computed(() => {
  if (props.message.progressMessage?.trim()) return props.message.progressMessage;
  if (props.currentRenderType === 'thinking') return 'Searching the knowledge base...';
  if (!isResponseInProgress.value) return 'ChatGDCE';
  return 'Preparing your response...';
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
      <div class="flex max-w-full flex-1 items-start gap-3 overflow-visible rounded-2xl px-3 py-3 sm:px-4">
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
            class="mb-2 flex min-w-0 items-center gap-2 text-sm text-slate-500 dark:text-zinc-400"
            :role="isResponseInProgress ? 'status' : undefined"
            :aria-live="isResponseInProgress ? 'polite' : undefined"
          >
            <span
              v-if="isResponseInProgress"
              class="h-2 w-2 shrink-0 rounded-full bg-blue-400 motion-safe:animate-pulse"
              aria-hidden="true"
            />
            <span class="truncate">{{ responseAvatarLabel }}</span>
          </div>

          <div
            v-if="(!isResponseInProgress && responseStateLabel) || generationDurationLabel || coverageBadge"
            class="mb-2 flex flex-wrap items-center gap-2 text-md text-gray-500 dark:text-zinc-500"
          >
            <span v-if="!isResponseInProgress && responseStateLabel" class="capitalize">
              {{ responseStateLabel }}
            </span>
            <span v-if="generationDurationLabel" class="tabular-nums">
              {{ generationDurationLabel }}
            </span>
            <span
              v-if="coverageBadge"
              class="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200"
              :title="coverageBadge.title"
            >
              {{ coverageBadge.label }}
            </span>
          </div>

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
