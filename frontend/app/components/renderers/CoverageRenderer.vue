<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();

const data = computed(() => {
  const content = props.block.content;
  if (!content || typeof content !== 'object' || Array.isArray(content)) {
    return {
      title: props.block.title || 'Information coverage',
      tone: 'info',
      items: [],
      note: '',
    };
  }

  const record = content as Record<string, unknown>;
  return {
    title: String(record.title || props.block.title || 'Information coverage'),
    tone: record.tone === 'warning' ? 'warning' : 'info',
    items: Array.isArray(record.items) ? record.items.map(String).filter(Boolean) : [],
    note: typeof record.note === 'string' ? record.note : '',
  };
});

const shellClass = computed(() =>
  data.value.tone === 'warning'
    ? 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-100'
    : 'border-sky-200 bg-sky-50 text-sky-950 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-100',
);

const markerClass = computed(() =>
  data.value.tone === 'warning'
    ? 'bg-amber-500 dark:bg-amber-400'
    : 'bg-sky-500 dark:bg-sky-400',
);
</script>

<template>
  <section
    v-if="data.items.length || data.note"
    class="my-4 rounded-lg border px-4 py-3"
    :class="shellClass"
  >
    <div class="flex items-center gap-2">
      <span class="h-2.5 w-2.5 shrink-0 rounded-full" :class="markerClass" />
      <h3 class="text-sm font-semibold">
        {{ data.title }}
      </h3>
    </div>

    <p v-if="data.note" class="mt-2 text-sm leading-6 opacity-90">
      {{ data.note }}
    </p>

    <ul v-if="data.items.length" class="mt-3 space-y-2 text-sm leading-6">
      <li v-for="item in data.items" :key="item" class="flex gap-2">
        <span class="mt-2 h-1.5 w-1.5 shrink-0 rounded-full opacity-70" :class="markerClass" />
        <span>{{ item }}</span>
      </li>
    </ul>
  </section>
</template>
