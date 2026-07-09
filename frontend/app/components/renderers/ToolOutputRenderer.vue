<script setup lang="ts">
import { LucideBraces, LucideLayoutGrid, LucideTable } from 'lucide-vue-next';
import type { MessageBlock } from '~/types/message';
import { useToolOutputRenderer } from '~/composables/renderers/useToolOutputRenderer';
import CodeBlockRenderer from './CodeBlockRenderer.vue';

const props = defineProps<{
  block: MessageBlock;
  loading?: boolean;
}>();

const { t } = useI18n();
const {
  toolName,
  activeView,
  cardEntries,
  tableColumns,
  tableRows,
  jsonBlock,
  canShowCards,
  canShowTable,
  setView,
  isLoading,
} = useToolOutputRenderer(() => props.block);
</script>

<template>
  <div
    class="tool-output-renderer overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800"
  >
    <div
      class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-200 bg-neutral-100 px-4 py-2 dark:border-neutral-700 dark:bg-neutral-800/60"
    >
      <span class="truncate text-xs font-bold uppercase tracking-widest text-neutral-600 dark:text-neutral-300">
        {{ toolName || t('toolOutput.title') }}
      </span>
      <div class="flex items-center gap-1">
        <button
          v-if="canShowCards"
          type="button"
          class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold transition-colors"
          :class="
            activeView === 'cards'
              ? 'bg-neutral-200 text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100'
              : 'text-neutral-500 hover:bg-neutral-200/70 dark:text-neutral-400 dark:hover:bg-neutral-700/70'
          "
          @click="setView('cards')"
        >
          <LucideLayoutGrid class="size-3.5" />
          {{ t('toolOutput.views.cards') }}
        </button>
        <button
          v-if="canShowTable"
          type="button"
          class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold transition-colors"
          :class="
            activeView === 'table'
              ? 'bg-neutral-200 text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100'
              : 'text-neutral-500 hover:bg-neutral-200/70 dark:text-neutral-400 dark:hover:bg-neutral-700/70'
          "
          @click="setView('table')"
        >
          <LucideTable class="size-3.5" />
          {{ t('toolOutput.views.table') }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold transition-colors"
          :class="
            activeView === 'json'
              ? 'bg-neutral-200 text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100'
              : 'text-neutral-500 hover:bg-neutral-200/70 dark:text-neutral-400 dark:hover:bg-neutral-700/70'
          "
          @click="setView('json')"
        >
          <LucideBraces class="size-3.5" />
          {{ t('toolOutput.views.json') }}
        </button>
      </div>
    </div>

    <div v-if="isLoading || loading" class="flex items-center justify-center p-8">
      <v-progress-circular indeterminate size="24" width="2" color="primary" />
    </div>

    <div
      v-else-if="activeView === 'cards' && canShowCards"
      class="grid gap-3 bg-white p-4 sm:grid-cols-2 dark:bg-zinc-950"
    >
      <div
        v-for="entry in cardEntries"
        :key="entry.key"
        class="rounded-lg border border-neutral-100 bg-zinc-50/80 p-3 dark:border-neutral-800 dark:bg-zinc-900/40"
      >
        <div class="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
          {{ entry.label }}
        </div>
        <div class="mt-1 break-words text-sm text-zinc-800 dark:text-zinc-200">
          {{ entry.value }}
        </div>
      </div>
    </div>

    <div
      v-else-if="activeView === 'table' && canShowTable"
      class="overflow-x-auto bg-white dark:bg-zinc-950"
    >
      <table class="w-full text-left text-sm">
        <thead class="border-b border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/50">
          <tr>
            <th
              v-for="col in tableColumns"
              :key="col.key"
              class="px-4 py-2 text-xs font-bold uppercase tracking-wider text-neutral-500"
            >
              {{ col.title }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in tableRows"
            :key="idx"
            class="border-b border-neutral-100 dark:border-neutral-900"
          >
            <td
              v-for="col in tableColumns"
              :key="col.key"
              class="px-4 py-3 text-neutral-800 dark:text-neutral-200"
            >
              {{ row[col.key] }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <CodeBlockRenderer v-else :block="jsonBlock" :loading="loading" />
  </div>
</template>
