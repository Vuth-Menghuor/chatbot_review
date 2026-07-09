<script setup lang="ts">
import { ref, toRef, computed } from 'vue';
import { LucideDownload, LucideRefreshCw } from 'lucide-vue-next';
import type { MessageBlock } from '~/types/message';
import { useChartRenderer } from '~/composables/renderers/useChartRenderer';
import EChartsPanel from '~/components/renderers/EChartsPanel.vue';
import BaseIconButton from '~/components/base/BaseIconButton.vue';
import ErrorRenderer from '~/components/renderers/ErrorRenderer.vue';

const props = defineProps<{ block: MessageBlock; loading?: boolean }>();
const emit = defineEmits<{
  (e: 'regenerate', messageId: string): void;
}>();

const { t } = useI18n();

const {
  invocation,
  title,
  headerIcon,
  toolName,
  taskId,
  hasChartData,
  echartsOption,
  isLoading,
  isError,
  errorMessage,
  chartOutput,
} = useChartRenderer(toRef(props, 'block'));

const chartTypeLabel = computed(() => {
  const raw = String(chartOutput.value?.chartType || 'chart').toLowerCase();
  const key = raw.replace(/\s+/g, '-');
  const translated = t(`chart.types.${key}`);
  if (translated !== `chart.types.${key}`) return translated;
  return t('chart.types.fallback', { type: raw });
});

const chartPanelRef = ref<InstanceType<typeof EChartsPanel> | null>(null);

const errorBlock = computed<MessageBlock>(() => ({
  id: `${props.block.id || 'chart'}-error`,
  type: 'error',
  content: {
    title: title.value || t('chart.title'),
    message: errorMessage.value || t('chart.error'),
    retryable: true,
    kind: 'server',
  },
  isComplete: true,
}));

function downloadChartPng() {
  const safe = `${title.value || 'chart'}.png`;
  chartPanelRef.value?.downloadPng(safe);
}

function retryChart() {
  emit('regenerate', taskId.value || props.block.id);
}
</script>

<template>
  <div
    class="chart-task-renderer group/chart overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800"
  >
    <div
      class="flex items-center justify-between gap-3 border-b border-neutral-200 bg-neutral-100 px-4 py-2 text-xs text-neutral-600 dark:border-neutral-700 dark:bg-neutral-800/60 dark:text-neutral-300"
    >
      <div class="flex min-w-0 items-center gap-2">
        <component :is="headerIcon" class="size-4 shrink-0 text-black dark:text-white" />
        <div class="min-w-0">
          <div class="truncate font-semibold text-neutral-900 dark:text-neutral-100">
            {{ title || chartTypeLabel }}
          </div>
          <div class="truncate font-mono uppercase tracking-widest">
            {{ chartTypeLabel }}
          </div>
        </div>
        <span
          v-if="toolName"
          class="shrink-0 rounded border border-neutral-300 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider dark:border-neutral-700"
        >
          {{ toolName }}
        </span>
      </div>

      <div class="flex items-center gap-1">
        <BaseIconButton
          v-if="isError"
          :icon="LucideRefreshCw"
          size="small"
          :tooltip="t('chart.regenerate')"
          tooltip-location="left"
          custom-class="text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"
          @click="retryChart"
        />
        <BaseIconButton
          v-if="invocation.state === 'output-available' && hasChartData"
          :icon="LucideDownload"
          size="small"
          :tooltip="$t('chat.actions.downloadPng')"
          tooltip-location="left"
          custom-class="text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"
          @click="downloadChartPng"
        />
      </div>
    </div>

    <div class="relative bg-white p-4 dark:bg-zinc-950">
      <div class="dot-pattern absolute inset-0 opacity-40" />
      <div class="relative z-10">
        <div v-if="isLoading || loading" class="chart-loading" role="status" aria-live="polite">
          <v-skeleton-loader type="image" class="chart-skeleton" />
          <div class="chart-loading-label">
            <v-progress-circular indeterminate size="18" width="2" />
            <span>{{ t('chart.generating') }}</span>
          </div>
        </div>

        <ErrorRenderer v-else-if="isError" :block="errorBlock" @retry="retryChart" />

        <EChartsPanel
          v-else-if="hasChartData"
          ref="chartPanelRef"
          :option="echartsOption"
          :height="320"
        />

        <div
          v-else
          class="rounded-md border border-dashed border-neutral-300 px-4 py-8 text-sm text-neutral-600 dark:border-neutral-700 dark:text-neutral-300"
        >
          {{ t('chart.empty') }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-loading {
  position: relative;
  min-height: 320px;
  overflow: hidden;
  border-radius: 8px;
}

.chart-skeleton,
.chart-skeleton :deep(.v-skeleton-loader__bone) {
  height: 320px;
  width: 100%;
}

.chart-loading-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.875rem;
}
</style>
