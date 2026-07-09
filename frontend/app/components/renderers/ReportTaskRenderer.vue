<script setup lang="ts">
import {
  LucideFileArchive,
  LucideFileCode2,
  LucideFileImage,
  LucideFileSpreadsheet,
  LucideFileText,
  LucideDownload,
} from 'lucide-vue-next';
import { computed, toRef } from 'vue';
import type { MessageBlock } from '~/types/message';
import { useReportRenderer } from '~/composables/renderers/useReportRenderer';

const props = defineProps<{
  block: MessageBlock;
  loading?: boolean;
  animate?: boolean;
  animId?: string;
}>();

const { data, shownStatus, handleDownload } = useReportRenderer(props);

const fileExtension = computed(() => {
  const fromFormat = data.value?.format?.toLowerCase().trim();
  if (fromFormat) return fromFormat;

  const title = data.value?.title || data.value?.toolName || '';
  const match = title.match(/\.([a-z0-9]+)$/i);
  return match?.[1]?.toLowerCase() || 'file';
});

const fileIcon = computed(() => {
  const ext = fileExtension.value;
  if (['xls', 'xlsx', 'csv'].includes(ext)) return LucideFileSpreadsheet;
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return LucideFileImage;
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return LucideFileArchive;
  if (['json', 'xml', 'yaml', 'yml', 'txt', 'md'].includes(ext)) return LucideFileCode2;
  return LucideFileText;
});
</script>

<template>
  <BaseCard
    custom-class="w-full bg-zinc-50 dark:bg-zinc-900/50"
    :class="props.loading ? 'animate-pulse' : ''"
  >
    <div
      v-if="shownStatus === 'pending' || shownStatus === 'processing'"
      class="flex h-full w-full flex-col items-center justify-center gap-2 p-6"
    >
      <v-skeleton-loader
        type="list-item-avatar-two-line"
        class="h-full w-full bg-zinc-100 p-4 dark:bg-zinc-800"
      />
      <p class="text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {{ $t('report.generating') }}
      </p>
    </div>
    <div
      v-else-if="shownStatus === 'error'"
      class="flex items-center justify-between gap-4 p-4 text-sm text-red-700 dark:text-red-300"
    >
      <div class="min-w-0">
        <h4 class="font-bold">{{ data?.title || data?.toolName || $t('report.title') }}</h4>
        <p class="mt-1 text-xs opacity-90">{{ data?.error || $t('report.error') }}</p>
      </div>
    </div>
    <div v-else class="flex items-center justify-between gap-4 p-4">
      <div class="min-w-0 flex items-center gap-3">
        <div
          class="h-10 w-10 rounded-lg bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 flex items-center justify-center"
        >
          <component :is="fileIcon" :size="18" class="text-zinc-500 dark:text-zinc-300" />
        </div>
        <div class="min-w-0">
          <h4 class="text-base font-bold text-zinc-800 dark:text-zinc-100 truncate">
            {{ data?.title || data?.toolName }}
          </h4>
          <div class="mt-1 flex items-center gap-2 text-xs text-zinc-500 font-medium">
            <span class="uppercase">{{ fileExtension }}</span>
            <span v-if="data?.fileSize">{{ data.fileSize }}</span>
          </div>
        </div>
      </div>
      <div class="shrink-0">
        <BaseIconButton
          v-if="shownStatus === 'completed'"
          :icon="LucideDownload"
          size="small"
          variant="flat"
          :tooltip="$t('chat.actions.downloadReport')"
          custom-class="bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300 shadow-md"
          @click="handleDownload"
        />
      </div>
    </div>
  </BaseCard>
</template>
