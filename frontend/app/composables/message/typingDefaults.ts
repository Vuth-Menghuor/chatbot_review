import type { TypingConfig } from '~/types/message';

export const defaultTypingConfig: TypingConfig = {
  baseDelayMs: 18,
  randomJitterMs: 12,
  flushIntervalMs: 24,
  sentencePauseMs: 130,
  clausePauseMs: 65,
  wordPauseMs: 16,
};
