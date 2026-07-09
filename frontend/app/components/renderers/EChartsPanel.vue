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

let resizeObserver: ResizeObserver | null = null;
let removeWindowResize: (() => void) | null = null;

function applyOption(opt: EChartsCoreOption | null | undefined) {
  const ch = chartRef.value;
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
  <div ref="rootRef" class="w-full min-h-0" :style="{ height: `${height}px` }" />
</template>
