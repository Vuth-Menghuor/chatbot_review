<script setup lang="ts">
import { ref, computed } from 'vue';
import { LucideTag } from 'lucide-vue-next';
import type { MessageBlock, PredictionTaxRate } from '~/types/message';
import { usePredictionRenderer } from '~/composables/renderers/usePredictionRenderer';
import SourceLink from '~/components/renderers/SourceLink.vue';

const props = defineProps<{
  block: MessageBlock;
  loading?: boolean;
  animate?: boolean;
  animId?: string;
}>();

const { t } = useI18n();
const {
  data,
  isHsMode,
  genericMetrics,
  genericTitle,
  shownConfidencePercent,
  isHighConfidence,
} = usePredictionRenderer(props);

const headerTitle = computed(() =>
  isHsMode.value
    ? data.value?.title || data.value?.toolName || t('prediction.title')
    : genericTitle.value || data.value?.toolName || t('prediction.genericTitle'),
);

// -1 represents the primary match; 0, 1, 2... represent alternative items
const activeItemIndex = ref(-1);

const selectedItem = computed(() => {
  if (activeItemIndex.value === -1 || !data.value?.alternatives?.[activeItemIndex.value]) {
    return {
      hsCode: data.value?.hsCode || '—',
      productName: data.value?.productName || '—',
      category: data.value?.category || '—',
      confidence: data.value?.confidence ?? 0,
      reason: data.value?.reason || '',
      importDuty: data.value?.importDuty,
      specialTax: data.value?.specialTax,
      vat: data.value?.vat,
      exportTax: data.value?.exportTax,
    };
  }
  const alt = data.value.alternatives?.[activeItemIndex.value];
  if (!alt) {
    return {
      hsCode: '—',
      productName: '—',
      category: '—',
      confidence: 0,
      reason: '',
    };
  }
  return {
    hsCode: alt.hsCode,
    productName: alt.productName,
    category: alt.category || data.value.category || '—',
    confidence: alt.confidence,
    reason: alt.reason || '',
    importDuty: alt.importDuty,
    specialTax: alt.specialTax,
    vat: alt.vat,
    exportTax: alt.exportTax,
  };
});

const taxRates = computed<PredictionTaxRate[]>(() => {
  if (Array.isArray(data.value?.taxRates) && data.value.taxRates.length > 0) {
    return data.value.taxRates.filter((rate) => rate?.label && rate?.value);
  }
  const fallback: PredictionTaxRate[] = [];
  if (selectedItem.value.importDuty) {
    fallback.push({ label: t('prediction.tax.importDuty'), value: selectedItem.value.importDuty });
  }
  if (selectedItem.value.specialTax) {
    fallback.push({ label: t('prediction.tax.specialTax'), value: selectedItem.value.specialTax });
  }
  if (selectedItem.value.vat) {
    fallback.push({ label: t('prediction.tax.vat'), value: selectedItem.value.vat });
  }
  if (selectedItem.value.exportTax) {
    fallback.push({ label: t('prediction.tax.exportTax'), value: selectedItem.value.exportTax });
  }
  return fallback;
});

const tariffSectionTitle = computed(
  () => data.value?.tariffSectionTitle || t('prediction.tariffSection'),
);
</script>

<template>
  <div
    class="prediction-renderer rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-800 group/prediction"
    :class="props.loading ? 'animate-pulse' : ''">
    <!-- Header with Label & Actions -->
    <div
      class="bg-neutral-100 dark:bg-neutral-800/60 px-4 py-2 text-xs font-mono text-neutral-600 dark:text-neutral-300 flex justify-between items-center border-b border-neutral-200 dark:border-neutral-700">
      <div class="flex items-center gap-2 min-w-0">
        <component :is="LucideTag" class="size-4 text-black dark:text-white shrink-0" />
        <span class="uppercase tracking-widest font-bold truncate">{{ headerTitle }}</span>
      </div>
      <BaseCopy v-if="isHsMode && selectedItem.hsCode !== '—'" :content="selectedItem.hsCode" button-variant="plain"
        class="text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100" />
    </div>

    <div class="flex flex-col gap-5 bg-white p-5 dark:bg-zinc-950">
      <template v-if="!isHsMode">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0 flex-1">
            <h3 class="text-2xl font-black leading-none tracking-tight text-zinc-900 dark:text-zinc-100">
              {{ genericMetrics[0]?.value ?? '—' }}
            </h3>
            <p v-if="genericMetrics[0]?.label" class="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {{ genericMetrics[0].label }}
            </p>
          </div>
          <div class="flex shrink-0 items-center justify-center self-center sm:self-auto">
            <v-progress-circular :model-value="(data.confidence ?? 0) * 100" :size="50" :width="6"
              :color="isHighConfidence ? 'success' : 'primary'" class="transition-all duration-300">
              <span class="text-sm font-black leading-none"
                :class="isHighConfidence ? 'text-emerald-600 dark:text-emerald-400' : 'text-primary'">
                {{ shownConfidencePercent }}%
              </span>
            </v-progress-circular>
          </div>
        </div>

        <div v-if="genericMetrics.length > 1" class="grid gap-3 sm:grid-cols-2">
          <div v-for="metric in genericMetrics.slice(1)" :key="metric.label"
            class="rounded-lg border border-neutral-100 bg-zinc-50/60 p-3 dark:border-neutral-800 dark:bg-zinc-900/40">
            <div class="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              {{ metric.label }}
            </div>
            <div class="mt-1 text-lg font-bold text-zinc-900 dark:text-zinc-100">
              {{ metric.value }}
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div v-if="data?.alternatives && data.alternatives.length > 0"
          class="flex flex-wrap gap-1.5 border-b border-neutral-100 dark:border-neutral-800 pb-3">
          <button class="px-3 py-1.5 rounded-full text-xs font-bold transition-all shrink-0" :class="activeItemIndex === -1
              ? 'bg-emerald-600 text-white shadow-sm'
              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
            " @click="activeItemIndex = -1">
            {{ t('prediction.primaryMatch', { percent: Math.round((data.confidence ?? 0) * 100) }) }}
          </button>
          <button v-for="(alt, idx) in data.alternatives" :key="idx"
            class="px-3 py-1.5 rounded-full text-xs font-bold transition-all shrink-0" :class="activeItemIndex === idx
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
              " @click="activeItemIndex = idx">
            {{
              t('prediction.alternative', {
                index: idx + 1,
                hsCode: alt.hsCode,
                percent: Math.round((alt.confidence ?? 0) * 100),
              })
            }}
          </button>
        </div>

        <!-- Primary Classification Details -->
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div class="flex-1 min-w-0">
            <h3 class="text-3xl font-black text-zinc-900 dark:text-zinc-100 tracking-tight font-mono leading-none">
              {{ selectedItem.hsCode }}
            </h3>
            <p class="text-md font-medium text-zinc-600 dark:text-zinc-400 mt-3 leading-relaxed">
              {{ selectedItem.productName }}
            </p>
          </div>

          <!-- Circular Confidence Meter -->
          <div class="flex items-center justify-center shrink-0 self-center sm:self-auto">
            <v-progress-circular :model-value="selectedItem.confidence * 100" :size="50" :width="6"
              bg-color="surface-light" class="transition-all duration-300"
              :color="isHighConfidence ? 'success' : 'primary'">
              <div class="flex flex-col items-center justify-center">
                <span class="text-sm -mr-1 font-black leading-none"
                  :class="isHighConfidence ? 'text-emerald-600 dark:text-emerald-400' : 'text-primary'">
                  {{ Math.round(selectedItem.confidence * 100) }}%
                </span>
              </div>
            </v-progress-circular>
          </div>
        </div>
      </template>

      <div v-if="selectedItem.reason"
        class="rounded-lg border border-neutral-100 bg-zinc-50/60 p-3 dark:border-neutral-800 dark:bg-zinc-900/40">
        <div class="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
          {{ t('prediction.reason') }}
        </div>
        <p class="mt-1 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
          {{ selectedItem.reason }}
        </p>
      </div>

      <div v-if="data?.evidence?.length" class="flex flex-col gap-2">
        <div class="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
          {{ t('prediction.evidence') }}
        </div>
        <ul class="list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
          <li v-for="(item, idx) in data.evidence" :key="idx">{{ item }}</li>
        </ul>
      </div>

      <SourceLink v-if="data?.sourceUrl" :title="data.sourceName || t('chat.filesPanel.sourceLabel')"
        :href="data.sourceUrl" />

      <div v-if="taxRates.length" class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-gray-400 dark:text-zinc-500 uppercase tracking-widest mb-1">
          {{ tariffSectionTitle }}
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div v-for="(rate, idx) in taxRates" :key="idx"
            class="flex flex-col p-3 rounded-lg border border-neutral-100 dark:border-neutral-800 bg-zinc-50/50 dark:bg-zinc-900/40">
            <span class="text-[12px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-tight">{{
              rate.label
              }}</span>
            <span class="text-lg font-extrabold text-emerald-600 dark:text-emerald-400 mt-2 leading-none">{{ rate.value
              }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
