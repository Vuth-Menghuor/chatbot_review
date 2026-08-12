import { z } from 'zod';
import type { NormalizedChatResponse } from '~/types/message';

const scalarSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const metricValueSchema = scalarSchema;
const rowSchema = z.record(z.string(), scalarSchema);
const metadataSchema = z.record(z.string(), z.unknown());

export const markdownBlockSchema = z.object({
  type: z.literal('markdown'),
  text: z.string().catch(''),
});

export const coverageBlockSchema = z.object({
  type: z.literal('coverage'),
  title: z.string().catch('Important limitation'),
  tone: z.enum(['info', 'warning']).optional().catch(undefined),
  items: z.array(z.string()).catch([]),
  note: z.string().optional().catch(undefined),
});

export const suggestionsBlockSchema = z.object({
  type: z.literal('suggestions'),
  title: z.string().optional().catch(undefined),
  items: z.array(z.string()).catch([]),
});

export const clarificationBlockSchema = z.object({
  type: z.literal('clarification'),
  title: z.string().optional().catch(undefined),
  questions: z.array(z.string()).catch([]),
});

export const tableBlockSchema = z.object({
  type: z.literal('table'),
  title: z.string().optional().catch(undefined),
  columns: z.array(z.object({
    key: z.string(),
    label: z.string(),
  })).catch([]),
  rows: z.array(rowSchema).catch([]),
});

export const summaryBlockSchema = z.object({
  type: z.literal('summary'),
  title: z.string().catch('Summary'),
  data: z.record(z.string(), scalarSchema).catch({}),
});

export const keyValueBlockSchema = z.object({
  type: z.literal('key_value'),
  title: z.string().catch('Details'),
  items: z.array(z.object({
    key: z.string(),
    value: scalarSchema,
  })).catch([]),
});

export const detailsBlockSchema = z.object({
  type: z.literal('details'),
  title: z.string().catch('Details'),
  items: z.array(z.object({
    title: z.string(),
    content: z.string(),
  })).catch([]),
  data: z.record(z.string(), z.unknown()).catch({}),
});

export const referencesBlockSchema = z.object({
  type: z.literal('references'),
  title: z.string().optional().catch(undefined),
  items: z.array(z.record(z.string(), scalarSchema)).catch([]),
});

export const officialReferenceBlockSchema = z.object({
  type: z.literal('official_reference'),
  title: z.string().catch('Official reference'),
  label: z.string().catch('Open official reference'),
  url: z.string().url().catch(''),
  agency: z.string().nullable().optional().catch(undefined),
  source_type: z.string().nullable().optional().catch(undefined),
});

export const chartBlockSchema = z.object({
  type: z.literal('chart'),
  title: z.string().optional().catch(undefined),
  data: z.record(z.string(), z.unknown()).catch({}),
});

export const predictionBlockSchema = z.object({
  type: z.literal('prediction'),
  title: z.string().catch('Preliminary HS Code'),
  data: z.record(z.string(), z.unknown()).catch({}),
});

export const errorBlockSchema = z.object({
  type: z.literal('error'),
  message: z.string().catch('Request failed'),
});

export const messageBlockSchema = z.discriminatedUnion('type', [
  markdownBlockSchema,
  coverageBlockSchema,
  suggestionsBlockSchema,
  clarificationBlockSchema,
  summaryBlockSchema,
  keyValueBlockSchema,
  tableBlockSchema,
  detailsBlockSchema,
  referencesBlockSchema,
  officialReferenceBlockSchema,
  chartBlockSchema,
  predictionBlockSchema,
  errorBlockSchema,
]);

const fallbackBlock = {
  type: 'fallback' as const,
  content: 'Unsupported response content',
};

export const safeMessageBlockSchema = z.preprocess((value) => {
  const result = messageBlockSchema.safeParse(value);
  if (result.success) return result.data;
  if (import.meta.dev) {
    console.warn('Unsupported normalized chat block', value);
  }
  return fallbackBlock;
}, z.union([
  messageBlockSchema,
  z.object({
    type: z.literal('fallback'),
    content: z.literal('Unsupported response content'),
  }),
]));

const coverageSchema = z.enum(['complete', 'partial', 'unknown']);
const confidenceSchema = z.enum(['high', 'medium', 'low']);
const statusSchema = z.enum(['completed', 'clarification_required', 'partial', 'failed', 'processing']);

const responseBodySchema = z.object({
  type: z.enum(['markdown', 'table', 'chart']).catch('markdown'),
  coverage: coverageSchema.catch('unknown'),
  confidence: confidenceSchema.optional().catch(undefined),
  summary: z.string().optional().catch(undefined),
  content: z.string().catch(''),
  limitations: z.array(z.object({
    code: z.string().optional().catch(undefined),
    message: z.string(),
  })).catch([]),
});

const publicErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  retryable: z.boolean().catch(false),
});

const citationSchema = z.object({
  id: z.string(),
  marker: z.number().int().positive().catch(1),
  label: z.string().optional().catch(undefined),
  title: z.string().optional().catch(undefined),
  snippet: z.string().optional().catch(undefined),
  url: z.string().nullable().optional().catch(undefined),
  score: z.number().nullable().optional().catch(undefined),
  citation_id: z.string().optional().catch(undefined),
  document_id: z.string().optional().catch(undefined),
  filename: z.string().optional().catch(undefined),
  chunk_index: z.number().int().optional().catch(undefined),
  retrieval_method: z.string().optional().catch(undefined),
  metadata: metadataSchema.catch({}),
});

export const normalizedChatResponseSchema = z.object({
  api_version: z.literal('1.0'),
  request_id: z.string(),
  session_id: z.string(),
  chat_id: z.string().nullable().optional().catch(undefined),
  project_id: z.string().nullable().optional().catch(undefined),
  status: statusSchema,
  service: z.string().nullable().optional().catch(undefined),
  intent: z.string(),
  query: z.string().nullable().optional().catch(undefined),
  language: z.string().nullable().optional().catch(undefined),
  coverage: coverageSchema.optional().catch(undefined),
  confidence: confidenceSchema.optional().catch(undefined),
  response: responseBodySchema.optional().catch(undefined),
  message: z.object({
    role: z.literal('assistant').catch('assistant'),
    content: z.array(safeMessageBlockSchema),
  }),
  citations: z.array(citationSchema),
  suggestions: z.array(z.string()),
  clarifications: z.array(z.string()).catch([]),
  errors: z.array(z.union([z.string(), publicErrorSchema])).catch([]),
  metrics: z.record(z.string(), metricValueSchema),
  debug: z.unknown().optional(),
});

export type ValidatedNormalizedChatResponse = z.infer<typeof normalizedChatResponseSchema>;

export function parseNormalizedChatResponse(value: unknown): ValidatedNormalizedChatResponse | null {
  const result = normalizedChatResponseSchema.safeParse(value);
  return result.success ? result.data : null;
}

export function isSchemaValidatedNormalizedChatResponse(
  value: unknown,
): value is NormalizedChatResponse {
  return parseNormalizedChatResponse(value) !== null;
}
