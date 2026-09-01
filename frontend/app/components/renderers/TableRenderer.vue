<template>
  <section class="my-2">
    <div
      class="table-renderer overflow-hidden rounded-md border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-zinc-950"
    >
      <div
        v-if="block.title || tableString"
        class="flex min-w-0 items-center justify-between gap-3 border-b border-neutral-200 bg-neutral-50 px-4 py-2.5 dark:border-neutral-800 dark:bg-neutral-900/50"
      >
        <h3
          v-if="block.title"
          class="min-w-0 truncate text-sm font-semibold leading-6 text-neutral-800 dark:text-neutral-100"
        >
          {{ block.title }}
        </h3>
        <div v-else class="min-w-0" />

        <BaseCopy
          :content="tableString"
          button-variant="text"
          size="small"
          color="neutral"
          custom-class="shrink-0"
        />
      </div>

      <div v-if="isStreamingLayout" class="flex items-center justify-center p-8">
        <v-progress-circular indeterminate size="24" width="2" color="primary" />
      </div>

      <div
        v-else-if="!columns.length || !visibleRows.length"
        class="flex items-center justify-center p-8 text-base leading-7 text-zinc-500 dark:text-zinc-400"
      >
        {{ $t('table.empty') }}
      </div>

      <div v-else ref="scrollRef" class="table-scroll max-h-[28rem] overflow-auto">
        <table
          class="w-full border-separate border-spacing-0 text-left text-base"
          :style="{ minWidth: tableMinWidth }"
        >
          <thead
            class="sticky top-0 z-10 bg-neutral-50 text-neutral-900 dark:bg-neutral-900 dark:text-neutral-100"
          >
            <tr>
              <th
                v-for="col in columns"
                :key="col.key"
                class="border-b border-r border-neutral-200 px-4 py-3 text-base font-semibold text-neutral-700 last:border-r-0 dark:border-neutral-800 dark:text-neutral-200"
                :class="cellClass(col.key, true)"
              >
                <span v-html="col.title"></span>
              </th>
            </tr>
          </thead>
          <TransitionGroup name="row-reveal" tag="tbody">
            <tr
              v-for="(row, idx) in visibleRows"
              :key="`row-${idx}`"
              class="transition-colors hover:bg-neutral-50/50 dark:hover:bg-neutral-800/10"
            >
              <td
                v-for="col in columns"
                :key="col.key"
                class="border-b border-r border-neutral-200 px-4 py-3 align-top font-normal text-neutral-700 last:border-r-0 dark:border-neutral-800 dark:text-neutral-200"
                :class="cellClass(col.key)"
              >
                <span
                  class="block min-w-0 leading-6"
                  :class="valueClass(col.key)"
                  v-html="displayCellValue(col.key, row[col.key])"
                ></span>
              </td>
            </tr>
          </TransitionGroup>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import type { MessageBlock } from '../../types/message';
import { useTableRenderer } from '~/composables/renderers/useTableRenderer';
import { filterClipboardTableColumns, tableToClipboardText } from '~/utils/table';

const props = defineProps<{
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}>();

const copyColumns = computed(() => filterClipboardTableColumns(rawColumns.value));

const {
  rawColumns,
  rawRows,

  columns,
  visibleRows,

  isStreamingLayout,
} = useTableRenderer(props);
const scrollRef = ref<HTMLDivElement | null>(null);

const tableString = computed(() => tableToClipboardText(copyColumns.value, rawRows.value));

const tableMinWidth = computed(() => {
  const base = Math.max(columns.value.length * 9, 44);
  return `${base}rem`;
});

function isNumericColumn(key: string) {
  return /(^|_)(value|display|amount|total|price|rate|score|raw|count|qty|quantity|percent|pct|year|month)(_|$)/i.test(
    key,
  );
}

function isCompactColumn(key: string) {
  return /(^|_)(rank|index|idx|no|number|row|order)(_|$)/i.test(key);
}

function isCodeColumn(key: string) {
  return /(^|_)(code|hs_code|period|date|unit|scale|country)(_|$)/i.test(key);
}

function cellClass(key: string, header = false) {
  if (isCompactColumn(key))
    return 'w-16 min-w-16 max-w-20 whitespace-nowrap text-left tabular-nums';
  if (isNumericColumn(key))
    return header ? 'text-left tabular-nums' : 'text-left tabular-nums whitespace-nowrap';
  if (isCodeColumn(key)) return 'w-32 min-w-28 whitespace-nowrap';
  return 'min-w-[16rem] max-w-[28rem]';
}

function valueClass(key: string) {
  if (isCompactColumn(key) || isNumericColumn(key) || isCodeColumn(key)) return 'whitespace-nowrap';
  return 'whitespace-normal break-words';
}

function displayCellValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '';
  }

  if (key.trim().toLowerCase() === 'growth_rate_pct') {
    return `${value}%`;
  }

  return String(value);
}

watch(
  () => props.block.id,
  async () => {
    await nextTick();
    if (scrollRef.value) {
      scrollRef.value.scrollLeft = 0;
      scrollRef.value.scrollTop = 0;
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.table-scroll {
  scrollbar-gutter: auto;
}

.table-scroll::-webkit-scrollbar {
  height: 10px;
  width: 10px;
}

.table-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(163 163 163 / 0.55);
}

.table-scroll::-webkit-scrollbar-track {
  background: transparent;
}
</style>
