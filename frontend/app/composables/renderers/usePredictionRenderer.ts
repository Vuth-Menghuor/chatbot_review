import { computed, onBeforeUnmount, ref, watch } from 'vue';
import type { MessageBlock, Prediction } from '~/types/message';
import { useRenderAnimation } from '../common/useRenderAnimation';

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
  const anim = useRenderAnimation();
  const data = computed<Prediction>(() => (props.block.content || {}) as Prediction);
  const showEvidence = ref(false);
  const shownConfidence = ref(0);
  let timer: ReturnType<typeof setInterval> | null = null;

  const stop = () => {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
  };

  watch(
    [
      () => data.value?.confidence,
      () => props.animate,
      () => props.animId,
      () => props.block.isComplete,
    ],
    ([target, enabled, _animId, streamComplete]) => {
      const nextTarget = Math.max(0, Math.min(1, Number(target ?? 0)));
      stop();
      if (streamComplete === false) {
        shownConfidence.value = nextTarget;
        return;
      }
      if (!enabled) {
        shownConfidence.value = nextTarget;
        return;
      }

      shownConfidence.value = 0;
      const steps = 24;
      const stepMs = Math.max(16, Math.floor(anim.predictionCountUpMs / steps));
      const step = nextTarget / steps;
      timer = setInterval(() => {
        const next = shownConfidence.value + step;
        if (next >= nextTarget) {
          shownConfidence.value = nextTarget;
          stop();
          return;
        }
        shownConfidence.value = next;
      }, stepMs);
    },
    { immediate: true },
  );

  onBeforeUnmount(stop);

  const shownConfidencePercent = computed(() => Math.round(shownConfidence.value * 100));

  const isHighConfidence = computed(() => (data.value?.confidence ?? 0) > 0.9);
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
    shownConfidence,
    shownConfidencePercent,
    isHighConfidence,
    isHsMode,
    genericMetrics,
    genericTitle,
  };
}
