<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();

const summary = computed(() => {
  const content = props.block.content;
  const record = content && typeof content === 'object' && !Array.isArray(content)
    ? (content as Record<string, unknown>)
    : {};
  const data = record.data && typeof record.data === 'object' && !Array.isArray(record.data)
    ? (record.data as Record<string, unknown>)
    : {};
  const total = data.total_tax ?? data.total ?? data.amount;
  const currency = data.currency;
  const entries = Object.entries(data)
    .filter(([key]) => !['total_tax', 'total', 'amount', 'currency', 'summary'].includes(key))
    .map(([key, value]) => ({ key: labelFor(key), value: formatValue(value) }));

  return {
    title: String(record.title || props.block.title || 'Summary'),
    total: formatValue(total),
    currency: currency ? String(currency) : '',
    summary: typeof data.summary === 'string' ? data.summary : '',
    entries,
  };
});

function labelFor(key: string) {
  const acronyms = new Set(['ATP', 'CIF', 'COP', 'CPP', 'DPP', 'HS', 'KHR', 'SOP', 'SPP', 'USD', 'VAT', 'VOP', 'VPP']);
  return key
    .replace(/_/g, ' ')
    .split(' ')
    .map((word) => {
      const upper = word.toUpperCase();
      if (acronyms.has(upper)) return upper;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(' ');
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'number') return value.toLocaleString();
  return String(value);
}
</script>

<template>
  <section class="my-4">
    <h3 class="mb-2 text-lg font-bold leading-7 text-neutral-950 dark:text-neutral-50">
      {{ summary.title }}
    </h3>
    <div v-if="summary.total" class="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span class="text-2xl font-bold text-neutral-950 dark:text-neutral-50">
        {{ summary.total }}
      </span>
      <span v-if="summary.currency" class="text-base font-semibold text-neutral-500 dark:text-neutral-400">
        {{ summary.currency }}
      </span>
    </div>
    <p v-if="summary.summary" class="mt-3 max-w-3xl text-base leading-7 text-neutral-700 dark:text-neutral-300">
      {{ summary.summary }}
    </p>
    <dl v-if="summary.entries.length" class="mt-4 grid gap-3 sm:grid-cols-2">
      <div v-for="entry in summary.entries" :key="entry.key">
        <dt class="text-xs font-medium text-neutral-500 dark:text-neutral-400">
          {{ entry.key }}
        </dt>
        <dd class="mt-1 text-base font-semibold leading-7 text-neutral-900 dark:text-neutral-100">
          {{ entry.value }}
        </dd>
      </div>
    </dl>
  </section>
</template>
