import { computed, ref } from 'vue';
import type { MessageBlock, Prediction } from '~/types/message';

/**
 * usePredictionRenderer
 * Exposes API `prediction` block `content` only (no default source URLs or labels).
 */
export function usePredictionRenderer(props: {
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}) {
  const { t } = useI18n();
  const data = computed<Prediction>(() => (props.block.content || {}) as Prediction);
  const showEvidence = ref(false);
  const isHsMode = computed(() => Boolean(data.value?.hsCode?.trim()));

  const genericMetrics = computed(() => {
    if (isHsMode.value) return [];
    if (Array.isArray(data.value?.metrics) && data.value.metrics.length) {
      return data.value.metrics;
    }
    const metrics: Array<{ label: string; value: string | number }> = [];
    const d = data.value;
    if (d.label || d.predictedVolume != null || d.value != null) {
      const unit = d.unit ? ` ${d.unit}` : '';
      metrics.push({
        label: d.label || t('prediction.valueLabel'),
        value:
          d.predictedVolume != null
            ? `${d.predictedVolume}${unit}`
            : `${d.value ?? '—'}${unit}`,
      });
    }
    if (d.year != null) {
      metrics.push({ label: t('prediction.year'), value: d.year });
    }
    return metrics;
  });

  const genericTitle = computed(
    () => data.value?.title || data.value?.label || data.value?.toolName || '',
  );

  return {
    data,
    showEvidence,
    isHsMode,
    genericMetrics,
    genericTitle,
  };
}
