<script setup lang="ts">
import type { EChartsCoreOption } from 'echarts/core';
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import { useTheme } from 'vuetify';
import { echarts, ensureEChartsRegistered } from '~/utils/chart';

const props = withDefaults(
  defineProps<{ option: EChartsCoreOption | null | undefined; height?: number }>(),
  { height: 300 },
);

const rootRef = ref<HTMLDivElement | null>(null);
const chartRef = shallowRef<ReturnType<typeof echarts.init> | null>(null);
const theme = useTheme();
const hasOption = ref(false);

let resizeObserver: ResizeObserver | null = null;
let removeWindowResize: (() => void) | null = null;

function applyOption(opt: EChartsCoreOption | null | undefined) {
  const ch = chartRef.value;
  hasOption.value = Boolean(opt);
  if (!ch) {
    return;
  }
  if (!opt) {
    ch.clear();
    return;
  }
  ch.setOption(opt, true);
  void nextTick(() => ch.resize());
}

onMounted(() => {
  void nextTick(() => {
    if (!rootRef.value || typeof window === 'undefined') {
      return;
    }
    ensureEChartsRegistered();
    chartRef.value = echarts.init(rootRef.value, undefined, { renderer: 'canvas' });
    applyOption(props.option);
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => chartRef.value?.resize());
      resizeObserver.observe(rootRef.value);
    } else {
      const onResize = () => chartRef.value?.resize();
      window.addEventListener('resize', onResize);
      removeWindowResize = () => window.removeEventListener('resize', onResize);
    }
  });
});

watch(
  () => props.option,
  (opt) => applyOption(opt),
  { deep: true },
);

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
  removeWindowResize?.();
  removeWindowResize = null;
  chartRef.value?.dispose();
  chartRef.value = null;
});

function chartBackgroundForExport(): string {
  return theme.global.current.value.dark ? '#09090b' : '#ffffff';
}

function downloadPng(filename = 'chart.png') {
  const ch = chartRef.value;
  if (!ch) {
    return;
  }
  const safeName = filename.replace(/[^\w.-]/g, '_') || 'chart.png';
  const url = ch.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: chartBackgroundForExport(),
  });
  const a = document.createElement('a');
  a.href = url;
  a.download = safeName;
  a.click();
}

defineExpose({ downloadPng });
</script>

<template>
  <div
    class="echarts-panel relative w-full overflow-hidden rounded-md bg-white dark:bg-zinc-950"
    :style="{ minHeight: `${height}px` }"
  >
    <div
      ref="rootRef"
      class="relative z-10 w-full"
      :style="{ height: `${height}px` }"
      role="img"
      aria-label="Chart visualization"
    />
    <div
      v-if="!hasOption"
      class="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-neutral-500 dark:text-neutral-400"
    >
      Chart data is not available.
    </div>
  </div>
</template>

<style scoped>
.echarts-panel {
  background-image:
    linear-gradient(to right, rgb(229 229 229 / 0.35) 1px, transparent 1px),
    linear-gradient(to bottom, rgb(229 229 229 / 0.35) 1px, transparent 1px);
  background-size: 48px 48px;
}

:global(.dark) .echarts-panel {
  background-image:
    linear-gradient(to right, rgb(63 63 70 / 0.35) 1px, transparent 1px),
    linear-gradient(to bottom, rgb(63 63 70 / 0.35) 1px, transparent 1px);
}
</style>
