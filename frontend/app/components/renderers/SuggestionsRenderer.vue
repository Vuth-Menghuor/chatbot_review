<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();
const emit = defineEmits<{
  (e: 'user-reply', payload: { requestId: string; action: string; values: Record<string, unknown> }): void;
}>();

const suggestions = computed(() => {
  const content = props.block.content;
  if (Array.isArray(content)) return content.map(String).filter(Boolean);
  if (content && typeof content === 'object' && Array.isArray((content as Record<string, unknown>).items)) {
    return ((content as Record<string, unknown>).items as unknown[]).map(String).filter(Boolean);
  }
  return [];
});

function sendSuggestion(text: string) {
  emit('user-reply', {
    requestId: props.block.id,
    action: 'send_suggestion',
    values: { message: text },
  });
}
</script>

<template>
  <div v-if="suggestions.length" class="my-4">
    <div class="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
      Suggested follow-ups
    </div>
    <div class="flex flex-wrap gap-2">
      <button
        v-for="suggestion in suggestions"
        :key="suggestion"
        type="button"
        class="rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-left text-sm text-zinc-700 transition hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
        @click="sendSuggestion(suggestion)"
      >
        {{ suggestion }}
      </button>
    </div>
  </div>
</template>
