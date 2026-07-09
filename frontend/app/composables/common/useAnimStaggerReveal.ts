import { computed, onBeforeUnmount, ref, watch } from 'vue';
import type { UseAnimStaggerRevealOptions } from '~/types/message';

export function useAnimStaggerReveal<T>({
  items,
  enabled,
  animId,
  intervalMs,
  initialVisible = 1,
  maxVisible,
}: UseAnimStaggerRevealOptions<T>) {
  const visibleCount = ref(0);
  const lastAnimId = ref<string | undefined>(undefined);
  let timer: ReturnType<typeof setInterval> | null = null;

  const stopTimer = () => {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
  };

  const totalTarget = computed(() => {
    const total = items.value.length;
    if (!total) return 0;
    return total;
  });

  const animatedTarget = computed(() => {
    const total = totalTarget.value;
    if (!total) return 0;
    return typeof maxVisible === 'number' ? Math.min(total, Math.max(0, maxVisible)) : total;
  });

  watch(
    [items, enabled, animId],
    ([nextItems, isEnabled, nextAnimId]) => {
      const total = nextItems.length;
      if (!total) {
        visibleCount.value = 0;
        stopTimer();
        lastAnimId.value = nextAnimId;
        return;
      }

      if (!isEnabled) {
        visibleCount.value = total;
        stopTimer();
        lastAnimId.value = nextAnimId;
        return;
      }

      // Animate only when animId changes to a new value.
      const isNew = Boolean(nextAnimId) && nextAnimId !== lastAnimId.value;
      if (!isNew) return;
      lastAnimId.value = nextAnimId;

      const target = animatedTarget.value;
      visibleCount.value = Math.min(initialVisible, target);
      stopTimer();
      timer = setInterval(() => {
        if (visibleCount.value >= target) {
          visibleCount.value = total;
          stopTimer();
          return;
        }
        visibleCount.value += 1;
      }, intervalMs);
    },
    { immediate: true },
  );

  const visibleItems = computed(() => items.value.slice(0, Math.max(0, visibleCount.value)));

  onBeforeUnmount(stopTimer);

  return { visibleItems, visibleCount };
}
