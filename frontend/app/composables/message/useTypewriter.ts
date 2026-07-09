import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue';
import type { TypingConfig, UseTypewriterOptions, UseTypewriterResult } from '~/types/message';
import { defaultTypingConfig } from './typingDefaults';

export function useTypewriter(
  target: Ref<string>,
  enabled: Ref<boolean>,
  options: UseTypewriterOptions = {},
): UseTypewriterResult {
  const config: TypingConfig = { ...defaultTypingConfig, ...(options.config ?? {}) };
  const maxCharsPerTick = options.maxCharsPerTick ?? 16;

  const visibleLength = ref(0);
  let rafId: number | null = null;
  let lastTickAt = 0;
  let pauseUntil = 0;

  const typedText = computed(() => target.value.slice(0, visibleLength.value));
  const done = computed(() => visibleLength.value >= target.value.length);
  const isTyping = computed(() => enabled.value && !done.value);

  function stopLoop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function startLoop() {
    if (rafId !== null) return;
    lastTickAt = 0;
    pauseUntil = 0;
    rafId = requestAnimationFrame(tick);
  }

  function tick(now: number) {
    rafId = null;

    if (!enabled.value) {
      visibleLength.value = target.value.length;
      return;
    }
    if (done.value) {
      return;
    }

    if (lastTickAt === 0) lastTickAt = now;
    const deltaMs = now - lastTickAt;
    lastTickAt = now;

    if (now < pauseUntil) {
      rafId = requestAnimationFrame(tick);
      return;
    }

    let budget = deltaMs;
    let advanced = 0;
    const text = target.value;

    while (budget > 0 && visibleLength.value < text.length && advanced < maxCharsPerTick) {
      const nextChar = text[visibleLength.value] ?? '';
      const cost = config.baseDelayMs + Math.random() * config.randomJitterMs;

      if (budget < cost) break;

      budget -= cost;
      visibleLength.value += 1;
      advanced += 1;

      const extraPause = punctuationPause(nextChar, config);
      if (extraPause > 0) {
        pauseUntil = now + extraPause;
        break;
      }
    }

    if (visibleLength.value < text.length || enabled.value) {
      rafId = requestAnimationFrame(tick);
    }
  }

  function flush() {
    visibleLength.value = target.value.length;
    stopLoop();
  }

  function reset() {
    visibleLength.value = 0;
    pauseUntil = 0;
    lastTickAt = 0;
  }

  watch(target, (next, prev) => {
    const prevText = prev ?? '';
    const nextText = next ?? '';
    const isPrefixContinuation = nextText.startsWith(prevText.slice(0, visibleLength.value));

    if (!isPrefixContinuation) {
      reset();
    } else if (visibleLength.value > nextText.length) {
      visibleLength.value = nextText.length;
    }

    if (enabled.value && nextText.length > visibleLength.value) {
      startLoop();
    } else if (!enabled.value) {
      visibleLength.value = nextText.length;
    }
  });

  watch(
    enabled,
    (isEnabled) => {
      if (isEnabled) {
        if (!done.value) startLoop();
      } else {
        stopLoop();
        visibleLength.value = target.value.length;
      }
    },
    { immediate: true },
  );

  onBeforeUnmount(stopLoop);

  return { typedText, isTyping, done, flush, reset };
}

function punctuationPause(char: string, config: TypingConfig): number {
  if (/[.!?]/.test(char)) return config.sentencePauseMs;
  if (/[,;:]/.test(char)) return config.clausePauseMs;
  if (/\s/.test(char)) return config.wordPauseMs;
  return 0;
}
