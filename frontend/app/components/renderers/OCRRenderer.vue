<script setup lang="ts">
import { computed, toRef } from 'vue';
import { LucideClipboard } from 'lucide-vue-next';
import type { MessageBlock } from '~/types/message';
import { useOCRRenderer } from '~/composables/renderers/useOCRRenderer';

const props = defineProps<{ block: MessageBlock; loading?: boolean }>();
const loading = computed(() => props.loading);
const { t } = useI18n();
const { data, accuracyPercent, visibleText, fieldEntries } = useOCRRenderer(toRef(props, 'block'));

const headerTitle = computed(() => data.value?.title || t('ocr.title'));
const showConfidence = computed(() => data.value?.confidence !== undefined);
</script>

<template>
  <div
    class="ocr-renderer group/ocr overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800"
    :class="loading ? 'animate-pulse' : ''"
  >
    <div
      class="flex items-center justify-between border-b border-neutral-200 bg-neutral-100 px-4 py-2 text-xs font-mono text-neutral-600 dark:border-neutral-700 dark:bg-neutral-800/60 dark:text-neutral-300"
    >
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <LucideClipboard class="size-4 shrink-0 text-black dark:text-white" />
        <span class="shrink-0 truncate font-bold uppercase tracking-widest">{{ headerTitle }}</span>
        <span
          v-if="showConfidence"
          class="shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
        >
          {{ t('ocr.accuracy', { percent: accuracyPercent }) }}
        </span>
        <span
          v-if="data?.pages"
          class="shrink-0 rounded bg-neutral-200 px-1.5 py-0.5 text-[10px] font-bold uppercase text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300"
        >
          {{ t('ocr.pages', { count: data.pages }) }}
        </span>
      </div>
      <BaseCopy
        :content="data?.text || ''"
        button-variant="plain"
        class="text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"
      />
    </div>

    <div
      v-if="fieldEntries.length"
      class="grid gap-2 border-b border-neutral-100 bg-white p-4 sm:grid-cols-2 dark:border-neutral-800 dark:bg-zinc-950"
    >
      <div
        v-for="entry in fieldEntries"
        :key="entry.key"
        class="rounded-lg border border-neutral-100 bg-zinc-50/80 p-3 dark:border-neutral-800 dark:bg-zinc-900/40"
      >
        <div class="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{{ entry.key }}</div>
        <div class="mt-1 text-sm text-zinc-800 dark:text-zinc-200">{{ entry.value }}</div>
      </div>
    </div>

    <div
      v-if="loading && !visibleText"
      class="flex items-center justify-center bg-zinc-50 p-8 dark:bg-zinc-900/40"
    >
      <v-progress-circular indeterminate size="24" width="2" color="primary" />
    </div>

    <div
      v-else
      class="whitespace-pre-wrap bg-zinc-50 p-4 font-sans text-[14px] leading-relaxed text-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300"
    >
      {{ visibleText }}
    </div>
  </div>
</template>
