import { computed, onBeforeUnmount, ref, watch, type MaybeRefOrGetter, toValue } from 'vue';
import type { MessageBlock, OCRData } from '~/types/message';
import { useClipboardCopy } from '~/composables/common/useClipboardCopy';

const INITIAL_VISIBLE_CHARS = 50;
const REVEAL_CHARS_PER_TICK = 28;
const REVEAL_TICK_MS = 30;

/**
 * useOCRRenderer
 * Manages clipboard copy state for the OCRRenderer component.
 * Accepts a reactive block source so streamed API payloads update the view.
 */
export function useOCRRenderer(blockSource: MaybeRefOrGetter<MessageBlock>) {
  const { copied, copyText: copyToClipboard } = useClipboardCopy();
  const visibleChars = ref(0);
  let revealTimer: ReturnType<typeof setInterval> | null = null;

  const block = computed(() => toValue(blockSource));
  const data = computed<OCRData>(() => block.value.content as OCRData);

  const accuracyPercent = computed(() =>
    data.value?.confidence != null ? (data.value.confidence * 100).toFixed(0) : '—',
  );
  const visibleText = computed(() => (data.value?.text || '').slice(0, visibleChars.value));
  const fieldEntries = computed(() => {
    const fields = data.value?.fields;
    if (!fields || typeof fields !== 'object') return [];
    return Object.entries(fields).map(([key, value]) => ({
      key,
      value: value == null ? '—' : String(value),
    }));
  });

  const stopRevealTimer = () => {
    if (!revealTimer) return;
    clearInterval(revealTimer);
    revealTimer = null;
  };

  watch(
    data,
    (nextData) => {
      const fullText = nextData?.text || '';
      if (!fullText) {
        visibleChars.value = 0;
        stopRevealTimer();
        return;
      }

      visibleChars.value = Math.min(INITIAL_VISIBLE_CHARS, fullText.length);
      stopRevealTimer();
      revealTimer = setInterval(() => {
        if (visibleChars.value >= fullText.length) {
          stopRevealTimer();
          return;
        }
        visibleChars.value += REVEAL_CHARS_PER_TICK;
      }, REVEAL_TICK_MS);
    },
    { immediate: true },
  );

  const copyText = async () => {
    if (!data.value?.text) return;
    await copyToClipboard(data.value.text);
  };

  onBeforeUnmount(stopRevealTimer);

  return {
    data,
    copied,
    accuracyPercent,
    visibleText,
    fieldEntries,
    copyText,
  };
}
