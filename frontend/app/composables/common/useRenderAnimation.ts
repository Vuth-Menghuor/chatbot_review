import type { RenderAnimationConfig } from '~/types/message';

const DEFAULTS: RenderAnimationConfig = {
  enabled: true,
  thinkingMs: 900,
  markdownChunkMs: 40,
  blockEnterMs: 280,
  tableRowMs: 120,
  workflowStepMs: 140,
  stepsStepMs: 130,
  ocrFieldMs: 90,
  predictionCountUpMs: 900,
  reportStatusMs: 650,
  jsonCharChunk: 24,
  jsonTickMs: 40,
  maxStaggerItems: 20,
};

export function useRenderAnimation(): RenderAnimationConfig {
  // Keep this synchronous + static for now (demo mode).
  // Later you can load overrides from a Pinia store or runtimeConfig.
  return DEFAULTS;
}
