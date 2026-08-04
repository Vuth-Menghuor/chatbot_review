<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();

const details = computed(() => {
  const content = props.block.content;
  const record = content && typeof content === 'object' && !Array.isArray(content)
    ? (content as Record<string, unknown>)
    : {};
  const data = record.data && typeof record.data === 'object' && !Array.isArray(record.data)
    ? (record.data as Record<string, unknown>)
    : {};
  const rawItems = Array.isArray(record.items) ? record.items : [];
  const rawAssumptions = Array.isArray(data.assumptions) ? data.assumptions : [];
  const rawRates = Array.isArray(data.ratesApplied) ? data.ratesApplied : [];
  return {
    title: String(record.title || props.block.title || 'Details'),
    items: rawItems
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
      .map((item) => ({
        title: String(item.title || 'Detail'),
        content: String(item.content || ''),
      }))
      .filter((item) => item.content),
    assumptions: rawAssumptions
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
      .map((item) => ({
        label: String(item.label || ''),
        value: String(item.value || ''),
        note: typeof item.note === 'string' ? item.note : '',
      }))
      .filter((item) => item.label || item.value),
    ratesApplied: rawRates
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
      .map((item) => ({
        code: String(item.code || ''),
        rate: String(item.rate || ''),
      }))
      .filter((item) => item.code || item.rate),
  };
});

const showAsStepCards = computed(() => details.value.title === 'Calculation Details');
const showStructuredAssumptions = computed(
  () =>
    details.value.title === 'Assumptions & Notes' &&
    (details.value.assumptions.length > 0 || details.value.ratesApplied.length > 0),
);
</script>

<template>
  <section
    v-if="details.items.length || showStructuredAssumptions"
    class="my-4 border-t border-neutral-200 pt-4 dark:border-neutral-800"
  >
    <h3 class="mb-4 text-lg font-bold leading-7 text-neutral-950 dark:text-neutral-50">
      {{ details.title }}
    </h3>

    <div v-if="showAsStepCards" class="space-y-3">
      <div
        v-for="(item, index) in details.items"
        :key="`${item.title}-${index}`"
        class="space-y-2"
      >
        <h4 class="text-base font-semibold leading-7 text-neutral-800 dark:text-neutral-200">
          {{ item.title }}
        </h4>
        <BaseInlineCard as="article">
          <pre class="whitespace-pre-wrap px-4 py-3 text-base leading-7 text-neutral-700 dark:text-neutral-300">{{ item.content }}</pre>
        </BaseInlineCard>
      </div>
    </div>

    <div v-else-if="showStructuredAssumptions" class="space-y-4">
      <BaseInlineCard v-if="details.assumptions.length">
        <div class="border-b border-neutral-100 px-4 py-3 text-base font-semibold leading-7 text-neutral-900 dark:border-neutral-900 dark:text-neutral-100">
          Assumptions
        </div>
        <dl class="grid gap-x-6 gap-y-3 px-4 py-3 sm:grid-cols-2">
          <div
            v-for="item in details.assumptions"
            :key="`${item.label}-${item.value}`"
            class="min-w-0"
          >
            <dt class="text-xs font-medium text-neutral-500 dark:text-neutral-400">
              {{ item.label }}
            </dt>
            <dd class="mt-1 break-words text-base leading-7 text-neutral-900 dark:text-neutral-100">
              {{ item.value }}
            </dd>
            <p v-if="item.note" class="mt-1 text-sm leading-6 text-neutral-500 dark:text-neutral-400">
              {{ item.note }}
            </p>
          </div>
        </dl>
      </BaseInlineCard>

      <BaseInlineCard v-if="details.ratesApplied.length">
        <div class="border-b border-neutral-100 px-4 py-3 text-base font-semibold leading-7 text-neutral-900 dark:border-neutral-900 dark:text-neutral-100">
          Rates Applied
        </div>
        <dl class="grid gap-x-6 gap-y-3 px-4 py-3 sm:grid-cols-4">
          <div
            v-for="item in details.ratesApplied"
            :key="`${item.code}-${item.rate}`"
            class="min-w-0"
          >
            <dt class="text-xs font-medium text-neutral-500 dark:text-neutral-400">
              {{ item.code }}
            </dt>
            <dd class="mt-1 break-words text-base leading-7 text-neutral-900 dark:text-neutral-100">
              {{ item.rate }}
            </dd>
          </div>
        </dl>
      </BaseInlineCard>
    </div>

    <div v-else class="space-y-2">
      <details
        v-for="(item, index) in details.items"
        :key="`${item.title}-${index}`"
        class="group"
        :open="index === 0"
      >
        <BaseInlineCard>
          <summary class="cursor-pointer px-4 py-3 text-base font-semibold leading-7 text-neutral-900 marker:text-neutral-400 dark:text-neutral-100">
            {{ item.title }}
          </summary>
          <pre class="whitespace-pre-wrap border-t border-neutral-100 px-4 py-3 text-base leading-7 text-neutral-700 dark:border-neutral-900 dark:text-neutral-300">{{ item.content }}</pre>
        </BaseInlineCard>
      </details>
    </div>
  </section>
</template>
