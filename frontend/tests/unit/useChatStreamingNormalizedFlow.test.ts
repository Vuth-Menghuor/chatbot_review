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
    responseStatus?: string;
    blocks?: MessageBlock[];
    sources?: MessageSource[];
    coverage?: string;
    confidence?: string;
    requestId?: string;
    chatId?: string;
    streamingContent?: string;
    normalizedResponse?: unknown;
    error?: string | null;
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

async function streamWithReactiveAssistant(events: Array<{ event: string; data: unknown }>) {
  installRuntimeConfig();
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.accessToken = 'test-token';

  const calls: UpsertCall[] = [];
  const currentRenderType = { value: 'idle' };
  const assistant: Message = {
    id: 'assistant-1',
    role: 'assistant',
    status: 'thinking',
    content: '',
  };
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
      assistant.content = content;
      assistant.status = meta?.status ?? assistant.status;
      assistant.blocks = meta?.blocks ?? assistant.blocks;
      assistant.streamingContent = meta?.streamingContent ?? assistant.streamingContent;
      assistant.normalizedResponse = meta?.normalizedResponse ?? assistant.normalizedResponse;
      assistant.error = meta?.error === undefined ? assistant.error : meta.error ?? undefined;
      calls.push({ messageId, content, meta });
    },
    getAssistantMessage: () => assistant,
    getUiBlockDelay: () => 0,
  };

  try {
    await useChatStreaming(deps).streamFromChatApi('What is the HS code for a laptop?', [], 'assistant-1');
  } finally {
    globalThis.fetch = originalFetch;
  }

  return { calls, assistant };
}

test('streamFromChatApi renders valid api_version 1.0 responses with normalized handler', async () => {
  const { calls } = await streamWithDonePayload(normalizedResponse());
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.messageId, 'assistant-1');
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'General answer from API layer.');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
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
  assert.equal(finalCall.meta?.status, 'error');
  assert.equal(finalCall.meta?.responseStatus, 'failed');
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
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
});

test('streamFromChatApi renders normalized start and done streams without delta events', async () => {
  const { calls, currentRenderType } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-1', chat_id: 'chat-1', status: 'processing' } },
    {
      event: 'done',
      data: normalizedResponse({
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Final answer without delta events.' },
            { type: 'suggestions', title: 'Suggested follow-ups', items: ['How do I classify my goods?'] },
          ],
        },
        suggestions: ['How do I classify my goods?'],
      }),
    },
  ]);
  const finalCall = calls.at(-1);
  const startCall = calls[0];

  assert.ok(startCall);
  assert.equal(startCall.content, '');
  assert.equal(startCall.meta?.status, 'streaming');
  assert.equal(startCall.meta?.responseStatus, 'processing');
  assert.equal(startCall.meta?.requestId, 'request-1');
  assert.equal(startCall.meta?.chatId, 'chat-1');
  assert.deepEqual(startCall.meta?.blocks, []);
  assert.ok(finalCall);
  assert.equal(calls.filter((call) => call.meta?.status === 'streaming').length, 1);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.generationDurationMs, 1234);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Final answer without delta events.');
  assert.deepEqual(finalCall.meta?.blocks?.[1]?.content, ['How do I classify my goods?']);
  assert.equal(finalCall.meta?.sources?.length, 1);
  assert.equal(currentRenderType.value, 'response');
});

test('streamFromChatApi renders structured retrieval blocks only after done', async () => {
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-retrieval', status: 'processing' } },
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
  assert.equal(calls.filter((call) => call.meta?.status === 'streaming').length, 1);
  assert.equal(calls.length, 2);
  assert.equal(calls[0]?.meta?.status, 'streaming');
  assert.equal(calls[0]?.meta?.responseStatus, 'processing');
  assert.equal(calls[0]?.meta?.requestId, 'request-retrieval');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'clarification_required');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table', 'clarification']);
  assert.equal(finalCall.meta?.blocks?.[1]?.content.rows[0].hs_code, '5208.39.00');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.equal((finalCall.meta?.normalizedResponse as Record<string, unknown>)?.request_id, 'request-retrieval');
});

test('streamFromChatApi treats delta text as temporary and done message.content as final truth', async () => {
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-authoritative', status: 'processing' } },
    { event: 'delta', data: { content: 'Temporary plain text while generating...' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-authoritative',
        service: 'retrieval',
        intent: 'hs_code_lookup',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'The HS code for a laptop is shown below.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'The HS code for a laptop is shown below.' },
            {
              type: 'table',
              title: 'Possible HS Codes',
              columns: [{ key: 'hs_code', label: 'HS Code' }],
              rows: [{ hs_code: '8471.30.00' }],
            },
          ],
        },
      }),
    },
  ]);

  const streamingCall = calls.find((call) => call.meta?.status === 'streaming' && call.content);
  const finalCall = calls.at(-1);

  assert.ok(streamingCall);
  assert.equal(streamingCall.content, 'Temporary plain text while generating...');
  assert.deepEqual(streamingCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(streamingCall.meta?.blocks?.[0]?.isComplete, false);
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.equal((finalCall.meta?.normalizedResponse as Record<string, unknown>)?.request_id, 'request-authoritative');
  assert.equal('mode' in (finalCall.meta?.normalizedResponse as Record<string, unknown>), false);
  assert.equal('transport' in (finalCall.meta?.normalizedResponse as Record<string, unknown>), false);
  assert.equal(finalCall.content, 'The HS code for a laptop is shown below.');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table']);
  assert.equal(finalCall.meta?.blocks?.[1]?.content.rows[0].hs_code, '8471.30.00');
  assert.equal(finalCall.content.includes('Temporary plain text'), false);
});

test('streamFromChatApi appends delta content into temporary markdown text', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-delta-append', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'The HS code for a lap' } },
    { event: 'delta', data: { content: 'top is' } },
    { event: 'delta', data: { content: ' 8471.30...' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-delta-append',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'The HS code for a laptop is 8471.30.00.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'The HS code for a laptop is 8471.30.00.' },
          ],
        },
      }),
    },
  ]);

  const streamingCalls = calls.filter((call) => call.meta?.status === 'streaming' && call.content);

  assert.deepEqual(streamingCalls.map((call) => call.content), [
    'The HS code for a lap',
    'The HS code for a laptop is',
    'The HS code for a laptop is 8471.30...',
  ]);
  assert.deepEqual(streamingCalls.map((call) => call.meta?.streamingContent), [
    'The HS code for a lap',
    'The HS code for a laptop is',
    'The HS code for a laptop is 8471.30...',
  ]);
  assert.deepEqual(streamingCalls.map((call) => call.meta?.blocks?.[0]?.type), ['markdown', 'markdown', 'markdown']);
  assert.equal(assistant.content, 'The HS code for a laptop is 8471.30.00.');
  assert.equal(assistant.streamingContent, '');
  assert.equal((assistant.normalizedResponse as Record<string, unknown>)?.request_id, 'request-delta-append');
});

test('streamFromChatApi keeps structured-looking delta text as temporary markdown only', async () => {
  const structuredLookingDelta = JSON.stringify({
    requestId: 'stream-fragment',
    mode: 'sync',
    status: 'success',
    tools: [
      {
        id: 'table-1',
        type: 'table',
        status: 'success',
        data: {
          columns: [{ key: 'hs_code', title: 'HS Code' }],
          rows: [{ hs_code: '8471.30.00' }],
        },
      },
    ],
  });
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-structured-delta', status: 'processing' } },
    { event: 'delta', data: { content: structuredLookingDelta } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-structured-delta',
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Final structured response.' },
            {
              type: 'table',
              title: 'Final Table',
              columns: [{ key: 'hs_code', label: 'HS Code' }],
              rows: [{ hs_code: '8471.30.00' }],
            },
          ],
        },
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Final structured response.',
          limitations: [],
        },
      }),
    },
  ]);

  const streamingCall = calls.find((call) => call.meta?.status === 'streaming' && call.content);
  const finalCall = calls.at(-1);

  assert.ok(streamingCall);
  assert.deepEqual(streamingCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(streamingCall.meta?.blocks?.[0]?.content, structuredLookingDelta);
  assert.ok(finalCall);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table']);
});

test('streamFromChatApi marks stream error while preserving partial delta text', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-error', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'The HS code result was partially generated.' } },
    { event: 'error', data: { detail: 'Main Chatbot Service stream interrupted' } },
  ]);

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'error');
  assert.equal(finalCall.meta?.responseStatus, 'failed');
  assert.equal(finalCall.meta?.error, 'Main Chatbot Service stream interrupted');
  assert.equal(finalCall.content, 'The HS code result was partially generated.');
  assert.equal(finalCall.meta?.streamingContent, 'The HS code result was partially generated.');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(assistant.status, 'error');
  assert.equal(assistant.error, 'Main Chatbot Service stream interrupted');
  assert.equal(assistant.content, 'The HS code result was partially generated.');
});

test('streamFromChatApi replaces calculator processing text with final structured blocks', async () => {
  const { calls, currentRenderType } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-calculator', status: 'processing' } },
    { event: 'delta', data: { content: 'Working on your request...' } },
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

  const streamingCall = calls.find((call) => call.meta?.status === 'streaming' && call.content);
  const finalCall = calls.at(-1);

  assert.equal(calls[0]?.meta?.status, 'streaming');
  assert.equal(calls[0]?.meta?.responseStatus, 'processing');
  assert.equal(calls[0]?.meta?.requestId, 'request-calculator');
  assert.ok(streamingCall);
  assert.equal(streamingCall.content, 'Working on your request...');
  assert.deepEqual(streamingCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.ok(finalCall);
  assert.equal(finalCall.messageId, 'assistant-1');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.content, 'Petroleum calculation complete.');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['summary', 'table']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content?.data?.total_tax, 2500000);
  assert.equal(finalCall.meta?.blocks?.some((block) => block.type === 'markdown' && block.content === 'Working on your request...'), false);
  assert.equal(currentRenderType.value, 'markdown');
});
