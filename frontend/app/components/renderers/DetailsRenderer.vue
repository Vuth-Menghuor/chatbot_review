<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

const props = defineProps<{ block: MessageBlock }>();

type DetailItem = { title: string; content: string };
type AssumptionLine = {
  key: string;
  text: string;
  kind: 'section' | 'line';
};

const details = computed(() => {
  const content = props.block.content;
  const record = content && typeof content === 'object' && !Array.isArray(content)
    ? (content as Record<string, unknown>)
    : {};
  const rawItems = Array.isArray(record.items) ? record.items : [];
  return {
    title: String(record.title || props.block.title || 'Details'),
    items: rawItems
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
      .map((item) => ({
        title: String(item.title || 'Detail'),
        content: String(item.content || ''),
      }))
      .filter((item) => item.content),
  };
});

const showAsStepCards = computed(() => details.value.title === 'Calculation Details');
const isAssumptionsBlock = computed(() => details.value.title === 'Assumptions & Notes');

function itemClipboardText(item: DetailItem) {
  return `${item.title}\n\n${item.content}`.trim();
}

const assumptionsText = computed(() => details.value.items.map((item) => item.content).join('\n\n'));
const assumptionLines = computed<AssumptionLine[]>(() =>
  assumptionsText.value
    .split(/\r?\n/)
    .map((line, index) => {
      const text = line.trim();
      const sectionMatch = text.match(/^=+\s*(.+?)\s*=+$/);
      return {
        key: `${text}-${index}`,
        text: sectionMatch?.[1]?.trim() || text,
        kind: sectionMatch ? 'section' : 'line',
      };
    })
    .filter((line) => line.text),
);
</script>

<template>
  <section
    v-if="details.items.length"
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
        <BaseInlineCard as="article" custom-class="relative group/detail-card">
          <BaseCopy
            :content="itemClipboardText(item)"
            button-variant="text"
            size="small"
            color="neutral"
            class="absolute right-2 top-2 opacity-0 transition-opacity group-hover/detail-card:opacity-100 focus-within:opacity-100"
          />
          <pre class="whitespace-pre-wrap px-4 py-3 pr-12 text-base leading-7 text-neutral-700 dark:text-neutral-300">{{ item.content }}</pre>
        </BaseInlineCard>
      </div>
    </div>

    <div v-else-if="isAssumptionsBlock">
      <BaseInlineCard custom-class="relative group/detail-card">
        <BaseCopy
          :content="assumptionsText"
          button-variant="text"
          size="small"
          color="neutral"
          class="absolute right-2 top-2 opacity-0 transition-opacity group-hover/detail-card:opacity-100 focus-within:opacity-100"
        />
        <ul class="space-y-2 px-4 py-3 pr-12 text-base leading-7 text-neutral-700 dark:text-neutral-300">
          <li
            v-for="line in assumptionLines"
            :key="line.key"
            class="break-words"
            :class="
              line.kind === 'section'
                ? 'mt-4 border-t border-neutral-100 pt-3 text-sm font-semibold uppercase leading-6 text-neutral-900 first:mt-0 first:border-t-0 first:pt-0 dark:border-neutral-800 dark:text-neutral-100'
                : ''
            "
          >
            {{ line.text }}
          </li>
        </ul>
      </BaseInlineCard>
    </div>

    <div v-else class="space-y-2">
      <details
        v-for="(item, index) in details.items"
        :key="`${item.title}-${index}`"
        class="group"
        :open="index === 0"
      >
        <BaseInlineCard custom-class="relative group/detail-card">
          <BaseCopy
            :content="itemClipboardText(item)"
            button-variant="text"
            size="small"
            color="neutral"
            class="absolute right-2 top-2 opacity-0 transition-opacity group-hover/detail-card:opacity-100 focus-within:opacity-100"
          />
          <summary class="cursor-pointer px-4 py-3 pr-12 text-base font-semibold leading-7 text-neutral-900 marker:text-neutral-400 dark:text-neutral-100">
            {{ item.title }}
          </summary>
          <pre class="whitespace-pre-wrap border-t border-neutral-100 px-4 py-3 pr-12 text-base leading-7 text-neutral-700 dark:border-neutral-900 dark:text-neutral-300">{{ item.content }}</pre>
        </BaseInlineCard>
      </details>
    </div>
  </section>
</template>
