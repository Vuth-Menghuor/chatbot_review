<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();

const references = computed(() => {
  const content = props.block.content;
  const record = content && typeof content === 'object' && !Array.isArray(content)
    ? (content as Record<string, unknown>)
    : {};
  const rawItems = Array.isArray(record.items) ? record.items : [];
  return {
    title: String(record.title || props.block.title || 'References'),
    items: rawItems
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
      .map((item, index) => ({
        id: String(item.id || index + 1),
        title: String(item.title || item.source || `Reference ${index + 1}`),
        url: typeof item.url === 'string' ? item.url : '',
        effectiveDate: typeof item.effective_date === 'string' ? item.effective_date : '',
      })),
  };
});
</script>

<template>
  <section v-if="references.items.length" class="my-4 border-t border-neutral-200 pt-4 dark:border-neutral-800">
    <details class="rounded-md border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-zinc-950">
      <summary class="cursor-pointer px-4 py-3 text-base font-bold leading-7 text-neutral-950 marker:text-neutral-400 dark:text-neutral-50">
        {{ references.title }}
      </summary>
      <ol class="space-y-3 border-t border-neutral-100 px-4 py-3 text-base leading-7 dark:border-neutral-900">
        <li v-for="item in references.items" :key="`${item.id}-${item.title}`" class="text-neutral-700 dark:text-neutral-300">
          <a
            v-if="item.url"
            :href="item.url"
            target="_blank"
            rel="noreferrer"
            class="font-medium text-sky-700 hover:underline dark:text-sky-300"
          >
            {{ item.title }}
          </a>
          <span v-else>{{ item.title }}</span>
          <span v-if="item.effectiveDate" class="ml-1 text-neutral-500 dark:text-neutral-400">
            Effective: {{ item.effectiveDate }}
          </span>
        </li>
      </ol>
    </details>
  </section>
</template>
