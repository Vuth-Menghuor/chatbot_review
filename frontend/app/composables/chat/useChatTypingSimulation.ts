import type { TypingConfig } from '~/types/message';
import { defaultTypingConfig } from '~/composables/message/typingDefaults';

export { defaultTypingConfig };

export function useChatTypingSimulation(config: TypingConfig = defaultTypingConfig) {
  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      setTimeout(resolve, ms);
    });

  async function applyNaturalPause(text: string) {
    const last = text.slice(-1);
    if (/[.!?]/.test(last)) return sleep(config.sentencePauseMs);
    if (/[,;:]/.test(last)) return sleep(config.clausePauseMs);
    if (/\s/.test(last)) return sleep(config.wordPauseMs);
    return Promise.resolve();
  }

  function getPiecePause(piece: string) {
    const last = piece.slice(-1);
    let pause = config.baseDelayMs + Math.random() * config.randomJitterMs;
    if (/[.!?]/.test(last)) pause += config.sentencePauseMs;
    else if (/[,;:]/.test(last)) pause += config.clausePauseMs;
    else if (/\s/.test(last)) pause += config.wordPauseMs;
    return pause;
  }

  return { config, sleep, applyNaturalPause, getPiecePause };
}
