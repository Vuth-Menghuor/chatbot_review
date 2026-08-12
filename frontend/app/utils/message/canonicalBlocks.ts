export const CANONICAL_BLOCK_TYPES = [
  'markdown',
  'reasoning',
  'summary',
  'key_value',
  'code',
  'table',
  'details',
  'references',
  'official_reference',
  'clarification',
  'image',
  'chart',
  'workflow',
  'ocr',
  'prediction',
  'report',
  'suggestions',
  'coverage',
  'interaction',
  'tool_output',
  'error',
  'fallback',
] as const;

export type CanonicalBlockType = (typeof CANONICAL_BLOCK_TYPES)[number];

const CANONICAL_BLOCK_SET = new Set<string>(CANONICAL_BLOCK_TYPES);

/**
 * Map of incoming/legacy/alias block type names to their canonical render type.
 * Unknown types fall back to `fallback` so they render safely as markdown.
 */
const BLOCK_TYPE_ALIASES: Record<string, CanonicalBlockType> = {
  text: 'markdown',
  md: 'markdown',
  plain: 'markdown',
  plaintext: 'markdown',

  thinking: 'reasoning',
  reason: 'reasoning',

  json: 'code',
  snippet: 'code',
  source: 'code',

  chart_task: 'chart',
  graph: 'chart',

  report_task: 'report',
  suggestion: 'suggestions',
  followups: 'suggestions',
  follow_ups: 'suggestions',
  partial_answer: 'coverage',
  limitations: 'coverage',
  not_found: 'coverage',

  tool: 'tool_output',
  toolresult: 'tool_output',
  tool_result: 'tool_output',
  mcp: 'tool_output',
  file: 'tool_output',
  structured: 'tool_output',

  steps: 'workflow',
  guide: 'workflow',
  procedure: 'workflow',

  // Formulas / calculations → markdown with code fences (ChatGPT-style)
  calculator: 'markdown',
  calc: 'markdown',
  math: 'markdown',
  formula: 'markdown',
  latex: 'markdown',
  mathjax: 'markdown',
  equation: 'markdown',
};

/**
 * Returns the canonical block type for any incoming type string.
 * Falls back to `'fallback'` for unknown values so renderers always have a strategy.
 */
export function canonicalizeBlockType(type: string | undefined | null): CanonicalBlockType {
  if (!type) return 'fallback';
  const normalized = type.toString().trim().toLowerCase();
  if (CANONICAL_BLOCK_SET.has(normalized)) return normalized as CanonicalBlockType;
  if (BLOCK_TYPE_ALIASES[normalized]) return BLOCK_TYPE_ALIASES[normalized] as CanonicalBlockType;
  return 'fallback';
}

/**
 * Apply alias-aware metadata adjustments when canonicalizing.
 * For example: `json` blocks should keep their original semantic by setting `meta.language = 'json'`
 * when normalized to `code`.
 */
export function canonicalizeBlock(block: {
  type: string;
  content?: unknown;
  meta?: Record<string, unknown>;
}): { type: CanonicalBlockType; meta?: Record<string, unknown> } {
  const rawType = (block.type || '').toString().trim().toLowerCase();
  const canonical = canonicalizeBlockType(rawType);

  let meta: Record<string, unknown> | undefined = block.meta;

  if (rawType === 'json' && canonical === 'code') {
    meta = { ...(meta || {}), language: meta?.language ?? 'json' };
  }

  return { type: canonical, meta };
}
