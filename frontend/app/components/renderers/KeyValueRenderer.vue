<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();

const data = computed(() => {
  const content = props.block.content;
  const record = content && typeof content === 'object' && !Array.isArray(content)
    ? (content as Record<string, unknown>)
    : {};
  const rawItems = Array.isArray(record.items) ? record.items : [];
  return {
    title: String(record.title || props.block.title || 'Information'),
    items: rawItems
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
      .map((item) => ({
        key: String(item.key || ''),
        value: item.value === null || item.value === undefined ? '' : String(item.value),
      }))
      .filter((item) => item.key || item.value),
  };
});
</script>

<template>
  <section v-if="data.items.length" class="my-4">
    <h3 class="mb-3 border-t border-neutral-200 pt-3 text-lg font-bold leading-7 text-neutral-950 dark:border-neutral-800 dark:text-neutral-50">
      {{ data.title }}
    </h3>
    <dl class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      <div v-for="item in data.items" :key="`${item.key}-${item.value}`" class="min-w-0">
        <dt class="text-xs font-medium text-neutral-500 dark:text-neutral-400">
          {{ item.key }}
        </dt>
        <dd class="mt-1 break-words text-base leading-7 text-neutral-900 dark:text-neutral-100">
          {{ item.value }}
        </dd>
      </div>
    </dl>
  </section>
</template>
