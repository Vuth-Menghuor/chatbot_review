<template>
  <section class="my-6">
    <h3
      v-if="block.title"
      class="mb-4 text-lg font-bold leading-7 text-neutral-950 dark:text-neutral-50"
    >
      {{ block.title }}
    </h3>

    <div
      class="table-renderer relative group/table overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800"
    >
      <!-- Integrated Copy Button -->
      <div class="absolute -right-1 z-10">
        <BaseCopy :content="tableString" button-variant="text" size="small" color="neutral" />
      </div>

      <div
        v-if="isStreamingLayout"
        class="p-8 flex items-center justify-center bg-white dark:bg-zinc-950"
      >
        <v-progress-circular indeterminate size="24" width="2" color="primary" />
      </div>

      <div
        v-else-if="!columns.length || !visibleRows.length"
        class="flex items-center justify-center bg-white p-8 text-base leading-7 text-zinc-500 dark:bg-zinc-950 dark:text-zinc-400"
      >
        {{ $t('table.empty') }}
      </div>

      <div v-else class="overflow-x-auto bg-white dark:bg-zinc-950">
        <table class="w-full text-base text-left border-collapse">
          <thead
            class="bg-neutral-50 dark:bg-neutral-900/50 border-b border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100"
          >
            <tr>
              <th
                v-for="col in columns"
                :key="col.key"
                class="px-4 py-3 font-bold text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 whitespace-nowrap"
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
                class="px-4 py-4 font-normal border-b border-neutral-100 dark:border-neutral-900 align-top text-neutral-800 dark:text-neutral-200 whitespace-nowrap"
              >
                <span v-html="row[col.key]"></span>
              </td>
            </tr>
          </TransitionGroup>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '../../types/message';
import { useTableRenderer } from '~/composables/renderers/useTableRenderer';
import { tableToClipboardText } from '~/utils/table';

const props = defineProps<{
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}>();

const { columns, visibleRows, isStreamingLayout } = useTableRenderer(props);

const tableString = computed(() => {
  return tableToClipboardText(columns.value, visibleRows.value);
});
</script>
