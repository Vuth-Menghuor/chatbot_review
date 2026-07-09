import { computed, isRef, onUnmounted, ref, watch, type Ref } from 'vue';

const SIZE = 4;
const GAP = 2;
const TOTAL_DOTS = SIZE * SIZE;

const PATTERNS = [
  [[0], [1], [2], [3], [7], [11], [15], [14], [13], [12], [8], [4], [5], [6], [10], [9]],
  [
    [0, 4, 8, 12],
    [1, 5, 9, 13],
    [2, 6, 10, 14],
    [3, 7, 11, 15],
  ],
  [
    [5, 6, 9, 10],
    [1, 4, 7, 8, 11, 14],
    [0, 3, 12, 15],
    [1, 4, 7, 8, 11, 14],
    [5, 6, 9, 10],
  ],
  [[0], [1, 4], [2, 5, 8], [3, 6, 9, 12], [7, 10, 13], [11, 14], [15]],
];

interface TypingIndicatorMatrixOptions {
  intervalMs?: number;
  active?: Ref<boolean> | boolean;
}

/** Dot-matrix thinking animation for `TypingIndicator.vue`. */
export function useTypingIndicatorMatrix(options: TypingIndicatorMatrixOptions | number = {}) {
  const intervalMs = typeof options === 'number' ? options : (options.intervalMs ?? 120);
  const activeSource = typeof options === 'number' ? true : (options.active ?? true);
  const isActive = computed(() => (isRef(activeSource) ? activeSource.value : activeSource));
  const activeDots = ref<Set<number>>(new Set());
  let patternIndex = 0;
  let stepIndex = 0;
  let matrixInterval: ReturnType<typeof setInterval> | undefined;

  function reset() {
    patternIndex = 0;
    stepIndex = 0;
    activeDots.value = new Set();
  }

  function stop() {
    if (!matrixInterval) return;
    clearInterval(matrixInterval);
    matrixInterval = undefined;
  }

  function nextStep() {
    const pattern = PATTERNS[patternIndex];
    if (!pattern) return;

    activeDots.value = new Set(pattern[stepIndex]);
    stepIndex += 1;

    if (stepIndex >= pattern.length) {
      stepIndex = 0;
      patternIndex = (patternIndex + 1) % PATTERNS.length;
    }
  }

  function start() {
    if (matrixInterval) return;
    nextStep();
    matrixInterval = setInterval(nextStep, intervalMs);
  }

  watch(
    isActive,
    (active) => {
      if (active) {
        start();
        return;
      }

      stop();
      reset();
    },
    { immediate: true },
  );

  onUnmounted(() => {
    stop();
    reset();
  });

  return {
    size: SIZE,
    gap: GAP,
    totalDots: TOTAL_DOTS,
    activeDots,
    reset,
    start,
    stop,
  };
}
