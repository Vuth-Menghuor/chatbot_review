import test from 'node:test';
import assert from 'node:assert/strict';
import { setActivePinia, createPinia } from 'pinia';

import { useChatStreaming } from '../../app/composables/chat/useChatStreaming';
import { useAuthStore } from '../../app/stores/auth.store';
import type { Message, MessageBlock, MessageSource, StreamingDeps } from '../../app/types/message';

type UpsertCall = {
  messageId: string;
  content: string;
  meta?: {
    generationDurationMs?: number;
    status?: string;
    blocks?: MessageBlock[];
    sources?: MessageSource[];
    coverage?: string;
    confidence?: string;
  };
};

function installRuntimeConfig() {
  const globalWithNuxt = globalThis as typeof globalThis & {
    useRuntimeConfig?: () => Record<string, unknown>;
  };
  globalWithNuxt.useRuntimeConfig = () => ({
    public: {
      allowedImageTypes: 'image/jpeg,image/png,image/webp',
      maxImageSizeMb: 5,
      gdceApiBaseUrl: 'http://localhost:8000',
    },
  });
}

function sseResponse(events: Array<{ event: string; data: unknown }>) {
  const body = events
    .map(({ event, data }) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('');
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function normalizedResponse(overrides: Record<string, unknown> = {}) {
  return {
    api_version: '1.0',
    request_id: 'request-1',
    session_id: 'session-1',
    status: 'completed',
    service: 'general',
    intent: 'general',
    message: {
      role: 'assistant',
      content: [
        {
          type: 'markdown',
          text: 'General answer from API layer.',
        },
      ],
    },
    citations: [
      {
        id: '1021',
        marker: 1,
        label: 'Source 1',
        title: 'Conditions for Import or Export',
        snippet: 'Conditions for Import or Export...',
        score: 0.9358,
        url: null,
        document_id: '1021',
        metadata: {},
      },
    ],
    suggestions: [],
    metrics: { latency_ms: 1234 },
    ...overrides,
  };
}

async function streamWithEvents(events: Array<{ event: string; data: unknown }>) {
  installRuntimeConfig();
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.accessToken = 'test-token';

  const calls: UpsertCall[] = [];
  const currentRenderType = { value: 'idle' };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => sseResponse(events)) as typeof fetch;

  const deps: StreamingDeps = {
    chatApi: {
      enabled: true,
      baseUrl: 'http://localhost:8000',
      apiToken: 'test-token',
      transport: 'gdce',
    },
    stopStreaming: { value: false },
    streamController: { value: null },
    currentRenderType,
    typing: {
      config: {},
      sleep: async () => {},
      applyNaturalPause: async () => {},
      getPiecePause: () => 0,
    },
    upsertAssistantMessage: (messageId, content, meta) => {
      calls.push({ messageId, content, meta });
    },
    getAssistantMessage: () => null as Message | null,
    getUiBlockDelay: () => 0,
  };

  try {
    await useChatStreaming(deps).streamFromChatApi('What documents do I need?', [], 'assistant-1');
  } finally {
    globalThis.fetch = originalFetch;
  }

  return { calls, currentRenderType };
}

async function streamWithDonePayload(payload: unknown) {
  return streamWithEvents([{ event: 'done', data: payload }]);
}

test('streamFromChatApi renders valid api_version 1.0 responses with normalized handler', async () => {
  const { calls } = await streamWithDonePayload(normalizedResponse());
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.messageId, 'assistant-1');
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'General answer from API layer.');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.generationDurationMs, 1234);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(finalCall.meta?.sources?.length, 1);
  assert.equal(finalCall.meta?.sources?.[0]?.id, '1021');
});

test('streamFromChatApi converts invalid versioned normalized contracts to safe error blocks', async () => {
  const { calls } = await streamWithDonePayload({
    api_version: '1.0',
    answer: 'This must not be passed to the legacy parser.',
  });
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'failed');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['error']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content?.message, 'The response format was not supported.');
  assert.equal(finalCall.content.includes('This must not be passed to the legacy parser.'), false);
});

test('streamFromChatApi leaves non-versioned responses for legacy parsing', async () => {
  const { calls } = await streamWithDonePayload({
    answer: 'Legacy answer from older endpoint.',
    status: 'completed',
  });
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Legacy answer from older endpoint.');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
});

test('streamFromChatApi renders normalized start and done streams without token events', async () => {
  const { calls, currentRenderType } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-1' } },
    {
      event: 'done',
      data: normalizedResponse({
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Final answer without token events.' },
            { type: 'suggestions', title: 'Suggested follow-ups', items: ['How do I classify my goods?'] },
          ],
        },
        suggestions: ['How do I classify my goods?'],
      }),
    },
  ]);
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(calls.some((call) => call.meta?.status === 'streaming'), false);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.generationDurationMs, 1234);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Final answer without token events.');
  assert.deepEqual(finalCall.meta?.blocks?.[1]?.content, ['How do I classify my goods?']);
  assert.equal(finalCall.meta?.sources?.length, 1);
  assert.equal(currentRenderType.value, 'thinking');
});

test('streamFromChatApi renders structured retrieval blocks only after done', async () => {
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-retrieval' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-retrieval',
        service: 'retrieval',
        intent: 'hs_code_lookup',
        status: 'clarification_required',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: 'Candidate HS codes are preliminary.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Candidate HS codes are preliminary.' },
            {
              type: 'table',
              title: 'Possible HS Code Matches',
              columns: [{ key: 'hs_code', label: 'HS Code' }],
              rows: [{ hs_code: '5208.39.00' }],
            },
            {
              type: 'clarification',
              title: 'More information is needed',
              questions: ['What is the fabric weight in g/m²?'],
            },
          ],
        },
        clarifications: ['What is the fabric weight in g/m²?'],
      }),
    },
  ]);
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(calls.some((call) => call.meta?.status === 'streaming'), false);
  assert.equal(calls.length, 1);
  assert.equal(finalCall.meta?.status, 'clarification_required');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table', 'clarification']);
  assert.equal(finalCall.meta?.blocks?.[1]?.content.rows[0].hs_code, '5208.39.00');
});

test('streamFromChatApi replaces calculator processing text with final structured blocks', async () => {
  const { calls, currentRenderType } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-calculator' } },
    { event: 'token', data: { content: 'Working on your request...' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-calculator',
        service: 'calculator',
        intent: 'calculation',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: 'Petroleum calculation complete.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            {
              type: 'summary',
              title: 'Import Tax Calculation',
              data: { total_tax: 2500000, currency: 'KHR' },
            },
            {
              type: 'table',
              title: 'Tax Breakdown',
              columns: [
                { key: 'component', label: 'component' },
                { key: 'amount', label: 'amount' },
              ],
              rows: [{ component: 'Phase 1', amount: 1200000 }],
            },
          ],
        },
      }),
    },
  ]);

  const streamingCall = calls.find((call) => call.meta?.status === 'streaming');
  const finalCall = calls.at(-1);

  assert.ok(streamingCall);
  assert.equal(streamingCall.content, 'Working on your request...');
  assert.ok(finalCall);
  assert.equal(finalCall.messageId, 'assistant-1');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.content, 'Petroleum calculation complete.');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['summary', 'table']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content?.data?.total_tax, 2500000);
  assert.equal(finalCall.meta?.blocks?.some((block) => block.type === 'markdown' && block.content === 'Working on your request...'), false);
  assert.equal(currentRenderType.value, 'markdown');
});
