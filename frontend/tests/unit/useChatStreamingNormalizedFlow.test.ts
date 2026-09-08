import test from 'node:test';
import assert from 'node:assert/strict';
import { setActivePinia, createPinia } from 'pinia';

import { useChatStreaming } from '../../app/composables/chat/useChatStreaming';
import { useAuthStore } from '../../app/stores/auth.store';
import { useChatStore } from '../../app/stores/chat.store';
import { useProjectStore } from '../../app/stores/project.store';
import type { Message, MessageBlock, MessageSource, StreamingDeps } from '../../app/types/message';

type UpsertCall = {
  messageId: string;
  content: string;
  meta?: {
    generationDurationMs?: number;
    status?: string;
    responseStatus?: string;
    responseMode?: string;
    progressStage?: string;
    progressMessage?: string;
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

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
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

async function streamWithEvents(
  events: Array<{ event: string; data: unknown }>,
  message = 'What documents do I need?',
) {
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
    await useChatStreaming(deps).streamFromChatApi(message, [], 'assistant-1');
  } finally {
    globalThis.fetch = originalFetch;
  }

  return { calls, currentRenderType };
}

async function streamWithDonePayload(payload: unknown) {
  return streamWithEvents([{ event: 'done', data: payload }]);
}

async function captureStreamRequestWithLocalState(setup: {
  chatBackendId?: string;
  projectBackendId?: string;
  includeProject?: boolean;
  startChatId?: string;
}) {
  installRuntimeConfig();
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.accessToken = 'test-token';
  const chatStore = useChatStore();
  const projectStore = useProjectStore();
  const project = setup.includeProject
    ? projectStore.addProject('Customs Project', 'Project workspace', setup.projectBackendId)
    : undefined;
  const chat = chatStore.createChat('New Chat', project?.id);
  if (setup.chatBackendId) chatStore.setBackendChatId(chat.id, setup.chatBackendId);

  let captured: Record<string, unknown> | null = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    captured = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
    return sseResponse([
      {
        event: 'start',
        data: {
          request_id: 'request-1',
          chat_id: setup.startChatId ?? '11111111-1111-4111-8111-111111111111',
          ...(setup.projectBackendId ? { project_id: setup.projectBackendId } : {}),
        },
      },
      { event: 'done', data: normalizedResponse() },
    ]);
  }) as typeof fetch;

  const deps: StreamingDeps = {
    chatId: chat.id,
    projectId: project?.id,
    chatApi: {
      enabled: true,
      baseUrl: 'http://localhost:8000',
      apiToken: 'test-token',
      transport: 'gdce',
    },
    stopStreaming: { value: false },
    streamController: { value: null },
    currentRenderType: { value: 'idle' },
    typing: {
      config: {},
      sleep: async () => {},
      applyNaturalPause: async () => {},
      getPiecePause: () => 0,
    },
    upsertAssistantMessage: () => {},
    getAssistantMessage: () => null,
    getUiBlockDelay: () => 0,
  };

  try {
    await useChatStreaming(deps).streamFromChatApi('hello', [], 'assistant-1');
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.notEqual(captured, null);
  return { body: captured!, chatStore, chat, project };
}

async function streamWithReactiveAssistant(
  events: Array<{ event: string; data: unknown }>,
  message = 'What is the HS code for a laptop?',
  response = sseResponse(events),
) {
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
  globalThis.fetch = (async () => response) as typeof fetch;

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
      assistant.responseStatus = meta?.responseStatus ?? assistant.responseStatus;
      assistant.blocks = meta?.blocks ?? assistant.blocks;
      assistant.streamingContent = meta?.streamingContent ?? assistant.streamingContent;
      assistant.responseMode = meta?.responseMode ?? assistant.responseMode;
      assistant.progressStage = meta?.progressStage ?? assistant.progressStage;
      assistant.progressMessage = meta?.progressMessage ?? assistant.progressMessage;
      assistant.normalizedResponse = meta?.normalizedResponse ?? assistant.normalizedResponse;
      assistant.error = meta?.error === undefined ? assistant.error : meta.error ?? undefined;
      calls.push({ messageId, content, meta });
    },
    getAssistantMessage: () => assistant,
    getUiBlockDelay: () => 0,
  };

  try {
    await useChatStreaming(deps).streamFromChatApi(message, [], 'assistant-1');
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

test('streamFromChatApi rejects non-normalized stream done responses', async () => {
  const { calls } = await streamWithDonePayload({
    answer: 'Legacy answer from older endpoint.',
    status: 'completed',
  });
  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'error');
  assert.equal(finalCall.meta?.responseStatus, 'failed');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['error']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content?.message, 'The response format was not supported.');
  assert.equal(finalCall.content.includes('Legacy answer'), false);
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
  assert.equal(startCall.meta?.responseMode, 'stream');
  assert.equal(startCall.meta?.progressStage, 'starting');
  assert.equal(startCall.meta?.requestId, 'request-1');
  assert.equal(startCall.meta?.chatId, 'chat-1');
  assert.deepEqual(startCall.meta?.blocks, []);
  assert.ok(finalCall);
  assert.ok(calls.filter((call) => call.meta?.status === 'streaming').length > 1);
  assert.ok(calls.some((call) => call.meta?.progressStage === 'rendering'));
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.generationDurationMs, 1234);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Final answer without delta events.');
  assert.deepEqual(finalCall.meta?.blocks?.[1]?.content, ['How do I classify my goods?']);
  assert.equal(finalCall.meta?.sources?.length, 1);
  assert.equal(currentRenderType.value, 'suggestions');
});

test('streamFromChatApi shows mode-aware startup progress', async () => {
  const cases = [
    ['sync', 'Preparing your response...'],
    ['async', 'Processing your request in the background...'],
    ['stream', 'Generating an answer...'],
  ] as const;

  for (const [mode, expectedProgress] of cases) {
    const { calls } = await streamWithEvents([
      { event: 'start', data: { request_id: `request-${mode}`, status: 'processing', mode } },
      { event: 'done', data: normalizedResponse({ request_id: `request-${mode}` }) },
    ]);

    assert.equal(calls[0]?.meta?.responseMode, mode);
    assert.equal(calls[0]?.meta?.progressMessage, expectedProgress);
  }
});

test('streamFromChatApi streams normalized trade chart blocks through the SSE path', async () => {
  const response = normalizedResponse({
    request_id: 'request-trade-chart',
    service: 'trade',
    intent: 'trade_query',
    response: {
      type: 'table',
      coverage: 'unknown',
      content: 'China was Cambodia\'s top sea import partner in 2024.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'China was Cambodia\'s top sea import partner in 2024.' },
        {
          type: 'table',
          title: 'Top import partners',
          columns: [{ key: 'partner', label: 'Partner' }],
          rows: [{ partner: 'China' }],
        },
        {
          type: 'chart',
          title: 'Import partners',
          data: {
            chartType: 'pie',
            data: [{ label: 'China', trade_value_usd: 12419875213.99 }],
            series: [{ key: 'trade_value_usd', name: 'Trade Value (USD)', type: 'pie' }],
          },
        },
      ],
    },
  });
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-trade-chart', chat_id: 'chat-1', status: 'processing' } },
    {
      event: 'progress',
      data: {
        request_id: 'request-trade-chart',
        status: 'processing',
        mode: 'stream',
        stage: 'rendering',
        message: 'Rendering response...',
      },
    },
    ...response.message.content.map((block) => ({ event: 'block', data: block })),
    { event: 'done', data: response },
  ], 'List the top 5 import partners for sea transport in 2024, show as pie chart!');
  const finalCall = calls.at(-1);

  assert.equal(calls[0]?.meta?.progressMessage, 'Generating an answer...');
  assert.ok(calls.some((call) => call.meta?.progressStage === 'rendering'));
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.responseMode, 'stream');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table', 'chart']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'China was Cambodia\'s top sea import partner in 2024.');
});

test('streamFromChatApi ignores generic trade markdown block and applies concise final response content', async () => {
  const genericTradeMarkdown = [
    'SUMMARY OF KEY FINDINGS:',
    '',
    'The provided trade data contains specific figures and statistics regarding international trade movements.',
    '',
    'DATA VISUALIZATION SUGGESTIONS:',
    '',
    'Bar charts to compare total import and export values.',
  ].join('\n');
  const response = normalizedResponse({
    request_id: 'request-trade-breakdown-2026',
    service: 'trade',
    intent: 'trade_query',
    response: {
      type: 'table',
      coverage: 'unknown',
      content: 'Cambodia\'s imports by partner country in 2026 are shown below.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Cambodia\'s imports by partner country in 2026 are shown below.' },
        {
          type: 'table',
          title: 'Imports by partner country',
          columns: [
            { key: 'period', label: 'Period' },
            { key: 'partner_country', label: 'Partner country' },
            { key: 'display', label: 'Value' },
          ],
          rows: [{ period: '2026', partner_country: 'China', display: '$3.28 billion' }],
        },
        {
          type: 'chart',
          title: 'Trade Share Breakdown',
          data: {
            chartType: 'bar',
            data: [{ partner_country: 'China', trade_value_usd: 3282093061.95 }],
            series: [{ key: 'trade_value_usd', name: 'Trade Value (USD)', type: 'bar' }],
          },
        },
      ],
    },
  });
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-trade-breakdown-2026', chat_id: 'chat-1', status: 'processing' } },
    { event: 'block', data: { type: 'markdown', text: genericTradeMarkdown } },
    { event: 'block', data: response.message.content[1] },
    { event: 'block', data: response.message.content[2] },
    { event: 'done', data: response },
  ], 'Show the breakdown of imports by partner country for 2026');
  const finalCall = calls.at(-1);

  assert.equal(calls.some((call) => call.content.includes('SUMMARY OF KEY FINDINGS')), false);
  assert.ok(finalCall);
  assert.equal(finalCall.content, 'Cambodia\'s imports by partner country in 2026 are shown below.');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table', 'chart']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Cambodia\'s imports by partner country in 2026 are shown below.');
});

test('streamFromChatApi suppresses generic trade deltas before final blocks', async () => {
  const genericTradeDelta = 'SUMMARY OF KEY FINDINGS:- The raw trade data provided contains the statistical figures and values required for analysis.';
  const { calls, currentRenderType } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-trade-monthly', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: genericTradeDelta } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-trade-monthly',
        service: 'trade',
        intent: 'trade_query',
        response: {
          type: 'table',
          coverage: 'unknown',
          content: 'China and Thailand monthly imports are shown below.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'China and Thailand monthly imports are shown below.' },
            {
              type: 'table',
              title: 'Monthly import trend',
              columns: [
                { key: 'month', label: 'Month' },
                { key: 'china', label: 'China' },
                { key: 'thailand', label: 'Thailand' },
              ],
              rows: [{ month: 'Jan', china: 1200000, thailand: 900000 }],
            },
            {
              type: 'chart',
              title: 'China vs Thailand imports',
              data: {
                chartType: 'line',
                data: [{ month: 'Jan', china: 1200000, thailand: 900000 }],
                series: [
                  { key: 'china', name: 'China', type: 'line' },
                  { key: 'thailand', name: 'Thailand', type: 'line' },
                ],
              },
            },
          ],
        },
      }),
    },
  ], 'Show the monthly trend comparing China vs Thailand imports');

  const genericStreamingCalls = calls.filter((call) => call.content.includes('SUMMARY OF KEY FINDINGS'));
  const finalCall = calls.at(-1);

  assert.equal(genericStreamingCalls.length, 0);
  assert.ok(finalCall);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table', 'chart']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'China and Thailand monthly imports are shown below.');
});

test('streamFromChatApi hides an untrusted direct-answer draft until the out-of-scope markdown is final', async () => {
  const refusal = 'I’m sorry, but I can’t help with that. I specialize in Cambodia Customs matters.';
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-out-of-scope', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'DIRECT ANSWER: To clear your goods, submit a SAD declaration.' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-out-of-scope',
        service: 'unknown',
        intent: 'out_of_scope',
        response: { type: 'markdown', coverage: 'unknown', content: refusal, limitations: [] },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: refusal },
            { type: 'suggestions', items: ['How do I classify my goods?'] },
          ],
        },
      }),
    },
  ], 'qwdqwdwdwqdwqdw');

  assert.equal(calls.some((call) => call.content.includes('DIRECT ANSWER:')), false);
  assert.equal(calls.at(-1)?.content, refusal);
  assert.deepEqual(calls.at(-1)?.meta?.blocks?.map((block) => block.type), [
    'markdown',
    'suggestions',
  ]);
});

test('streamFromChatApi suppresses generic chart deltas before done', async () => {
  const genericTradeDelta = 'SUMMARY OF KEY FINDINGS:- The provided trade data contains specific figures and insights regarding trade volumes and statistics.';
  const { calls, currentRenderType } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-bar-followup', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: genericTradeDelta } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-bar-followup',
        service: 'trade',
        intent: 'trade_query',
        response: {
          type: 'chart',
          coverage: 'unknown',
          content: 'Here is the same data as a bar chart.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Here is the same data as a bar chart.' },
            {
              type: 'chart',
              title: 'Imports by partner',
              data: {
                chartType: 'bar',
                data: [{ label: 'China', trade_value_usd: 12419875213.99 }],
                series: [{ key: 'trade_value_usd', name: 'Trade Value (USD)', type: 'bar' }],
              },
            },
          ],
        },
      }),
    },
  ], 'now i want it as bar chart');

  const genericStreamingCalls = calls.filter((call) => call.content.includes('SUMMARY OF KEY FINDINGS'));
  const finalCall = calls.at(-1);

  assert.equal(genericStreamingCalls.length, 0);
  assert.ok(finalCall);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'chart']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Here is the same data as a bar chart.');
});

test('streamFromChatApi suppresses split generic deltas then applies final trade-balance answer', async () => {
  const genericTradeDelta = 'SUMMARY OF KEY FINDINGS: The provided trade data contains specific figures and insights.';
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-trade-balance', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'SUMMARY OF' } },
    { event: 'delta', data: { content: genericTradeDelta.slice('SUMMARY OF'.length) } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-trade-balance',
        service: 'trade',
        intent: 'trade_query',
        response: { type: 'markdown', coverage: 'unknown', content: 'The 2025 trade balance is shown below.', limitations: [] },
        message: { role: 'assistant', content: [{ type: 'markdown', text: 'The 2025 trade balance is shown below.' }] },
      }),
    },
  ], 'What is the trade balance with Thailand for 2025?');

  const genericStreamingCalls = calls.filter((call) => call.content.includes('SUMMARY OF KEY FINDINGS'));
  const finalStreamingCalls = calls.filter((call) => call.content.includes('The 2025 trade balance'));

  assert.equal(genericStreamingCalls.length, 0);
  assert.ok(finalStreamingCalls.length > 0);
  assert.equal(calls.at(-1)?.meta?.blocks?.[0]?.content, 'The 2025 trade balance is shown below.');
});

test('streamFromChatApi renders a genuine trade delta before done', async () => {
  const liveTradeDelta = 'Cambodia recorded a trade deficit with Thailand in 2025. ';
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-live-trade', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: liveTradeDelta } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-live-trade', service: 'trade', intent: 'trade_query',
        response: { type: 'markdown', coverage: 'unknown', content: 'Final trade balance.', limitations: [] },
        message: { role: 'assistant', content: [{ type: 'markdown', text: 'Final trade balance.' }] },
      }),
    },
  ], 'What is the trade balance with Thailand for 2025?');

  assert.ok(calls.some((call) => call.content.includes(liveTradeDelta)));
  assert.equal(calls.at(-1)?.content, 'Final trade balance.');
});

test('streamFromChatApi streams simple markdown-only done responses when no delta arrives', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-simple', chat_id: 'chat-1', status: 'processing' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-simple',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Hello! How can I help you today?',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Hello! How can I help you today?' },
          ],
        },
      }),
    },
  ]);

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);
  const finalCall = calls.at(-1);

  assert.ok(streamingCalls.length > 0);
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.content, 'Hello! How can I help you today?');
  assert.equal(assistant.streamingContent, '');
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
  assert.ok(calls.filter((call) => call.meta?.status === 'streaming').length > 1);
  assert.ok(calls.length > 2);
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

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);
  const streamingCall = streamingCalls.at(-1);
  const finalCall = calls.at(-1);

  assert.ok(streamingCalls.length > 1);
  assert.equal(streamingCalls[0]?.content, 'Temp');
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

test('streamFromChatApi replaces temporary delta with rich calculator done blocks', async () => {
  const temporaryText = 'Temporary plain text';
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-calculator-rich', status: 'processing' } },
    { event: 'delta', data: { content: temporaryText } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-calculator-rich',
        service: 'calculator',
        intent: 'calculation',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Import tax calculation complete.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'summary', title: 'Import Tax Calculation', data: { total_tax: 123 } },
            { type: 'key_value', title: 'Product Information', items: [{ key: 'HS Code', value: '8703.24.00' }] },
            { type: 'key_value', title: 'Input Parameters', items: [{ key: 'CIF', value: '40000 USD' }] },
            {
              type: 'table',
              title: 'Tax Breakdown',
              columns: [{ key: 'component', label: 'Component' }],
              rows: [{ component: 'Customs duty' }],
            },
            { type: 'details', title: 'Calculation Details', items: [{ title: 'Step 1', content: 'Calculate duty.' }] },
            { type: 'details', title: 'Assumptions & Notes', items: [{ title: 'Note', content: 'ACFTA applied.' }] },
          ],
        },
      }),
    },
  ], 'calculate import tax for hs code 8703.24.00 cif 40000 USD from China ACFTA DV=0 DQ=40%');

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), [
    'summary',
    'key_value',
    'key_value',
    'table',
    'details',
    'details',
  ]);
  assert.equal(finalCall.content.includes(temporaryText), false);
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.equal(assistant.streamingContent, '');
});

test('streamFromChatApi updates assistant mode and status from progress events before final done', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-progress', chat_id: 'chat-1', status: 'pending', mode: 'stream' } },
    {
      event: 'progress',
      data: {
        request_id: 'request-progress',
        chat_id: 'chat-1',
        status: 'processing',
        mode: 'stream',
        stage: 'retrieving',
        message: 'Searching customs documents...',
      },
    },
    { event: 'delta', data: { content: 'Real-time answer' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-progress',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Real-time answer',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Real-time answer' },
          ],
        },
      }),
    },
  ]);

  const progressCall = calls.find((call) => call.meta?.progressStage === 'retrieving');
  const deltaCall = calls.find((call) => call.content === 'Real-time answer' && call.meta?.status === 'streaming');
  const finalCall = calls.at(-1);

  assert.ok(progressCall);
  assert.equal(progressCall.meta?.responseMode, 'stream');
  assert.equal(progressCall.meta?.responseStatus, 'processing');
  assert.equal(progressCall.meta?.progressMessage, 'Searching customs documents...');
  assert.ok(deltaCall);
  assert.equal(deltaCall.meta?.responseMode, 'stream');
  assert.equal(deltaCall.meta?.progressStage, 'streaming');
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.responseMode, 'stream');
  assert.equal(finalCall.meta?.progressStage, 'completed');
  assert.equal(assistant.responseMode, 'stream');
  assert.equal(assistant.responseStatus, 'completed');
  assert.equal(assistant.progressStage, 'completed');
});

test('streamFromChatApi applies final structured blocks immediately after streamed text', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-progressive-blocks', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'Temporary preliminary answer.' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-progressive-blocks',
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
            { type: 'suggestions', title: 'Suggested follow-ups', items: ['What import duty applies?'] },
          ],
        },
        suggestions: ['What import duty applies?'],
      }),
    },
  ]);

  const finalCall = calls.at(-1);

  assert.equal(calls.some((call) => call.meta?.progressStage === 'rendering'), false);
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.progressStage, 'completed');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'table', 'suggestions']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'The HS code for a laptop is shown below.');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.equal(assistant.blocks?.length, 3);
  assert.equal(assistant.streamingContent, '');
});

test('streamFromChatApi ignores SSE block events and uses done as the only structured source', async () => {
  const finalPayload = normalizedResponse({
    request_id: 'request-block-stream',
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
          type: 'clarification',
          title: 'More information is needed',
          questions: ['Which BMW model is this?'],
        },
      ],
    },
    clarifications: ['Which BMW model is this?'],
  });
  const { calls } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-block-stream', status: 'processing' } },
    { event: 'block', data: finalPayload.message.content[0] },
    { event: 'block', data: finalPayload.message.content[1] },
    { event: 'done', data: finalPayload },
  ]);

  const renderingCalls = calls.filter((call) => call.meta?.progressStage === 'rendering');
  const finalCall = calls.at(-1);

  assert.ok(renderingCalls.length > 0);
  assert.deepEqual(renderingCalls.at(-1)?.meta?.blocks?.map((block) => block.type), [
    'markdown',
    'clarification',
  ]);
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.progressStage, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'clarification_required');
});

test('streamFromChatApi does not replay markdown blocks that duplicate streamed deltas', async () => {
  const finalPayload = normalizedResponse({
    request_id: 'request-duplicate-markdown',
    response: {
      type: 'markdown',
      coverage: 'complete',
      content: 'GDCE is Cambodia\'s General Department of Customs and Excise.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'GDCE is Cambodia\'s General Department of Customs and Excise.' },
        { type: 'suggestions', title: 'Related questions', items: ['How is customs duty calculated?'] },
      ],
    },
  });
  const deltaText = 'GDCE is Cambodia\'s General Department of Customs and Excise.';
  const { calls } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-duplicate-markdown', status: 'processing' } },
    { event: 'delta', data: { content: deltaText } },
    { event: 'block', data: finalPayload.message.content[0] },
    { event: 'block', data: finalPayload.message.content[1] },
    { event: 'done', data: finalPayload },
  ]);

  const markdownStreamingCalls = calls.filter((call) =>
    call.meta?.progressStage === 'streaming' && call.meta.blocks?.[0]?.type === 'markdown',
  );
  const finalCall = calls.at(-1);

  assert.ok(markdownStreamingCalls.length > 1);
  assert.equal(markdownStreamingCalls.at(-1)?.content, deltaText);
  assert.ok(markdownStreamingCalls.every((call, index, calls) =>
    index === 0 || call.content.startsWith(calls[index - 1]!.content),
  ));
  assert.ok(finalCall);
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(finalCall.meta?.blocks?.[0]?.id, 'assistant-1-streaming-markdown');
  assert.equal(finalCall.meta?.blocks?.[0]?.content, deltaText);
  assert.equal(finalCall.meta?.blocks?.[0]?.isComplete, true);
});

test('streamFromChatApi keeps general answer visible after matching done markdown', async () => {
  const answer =
    'Hello! I’m here to help you with Cambodia customs and trade questions. How can I assist you today?';

  const { calls, assistant } = await streamWithReactiveAssistant([
    {
      event: 'start',
      data: {
        request_id: 'hello-general',
        status: 'processing',
      },
    },
    {
      event: 'delta',
      data: {
        content: answer,
      },
    },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'hello-general',
        service: 'general',
        intent: 'general',
        status: 'completed',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: answer,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            {
              type: 'markdown',
              text: answer,
            },
          ],
        },
      }),
    },
  ], 'Hello');

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.content, answer);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(finalCall.meta?.blocks?.[0]?.id, 'assistant-1-streaming-markdown');
  assert.equal(finalCall.meta?.blocks?.[0]?.content, answer);
  assert.equal(finalCall.meta?.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.content, answer);
  assert.equal(assistant.blocks?.[0]?.content, answer);
  assert.equal(assistant.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.streamingContent, '');
  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
});

test('streamFromChatApi replaces streamed general text with different authoritative done markdown', async () => {
  const streamed = 'Hello! I\'m here to help...';
  const finalAnswer = 'Hello! I\'m here to help you with Cambodia customs and trade questions.';

  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'hello-general-revised', status: 'processing' } },
    { event: 'delta', data: { content: streamed } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'hello-general-revised',
        service: 'general',
        intent: 'general',
        status: 'completed',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: finalAnswer,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: finalAnswer },
          ],
        },
      }),
    },
  ], 'Hello');

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.content, finalAnswer);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(finalCall.meta?.blocks?.filter((block) => block.type === 'markdown').length, 1);
  assert.equal(finalCall.meta?.blocks?.[0]?.id, 'assistant-1-streaming-markdown');
  assert.equal(finalCall.meta?.blocks?.[0]?.content, finalAnswer);
  assert.equal(finalCall.meta?.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.content, finalAnswer);
  assert.equal(assistant.blocks?.[0]?.content, finalAnswer);
  assert.equal(assistant.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.streamingContent, '');
});

test('streamFromChatApi applies completed table content once it arrives in done', async () => {
  const { calls } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-table-stream', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'Candidate HS codes are below.' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-table-stream',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Candidate HS codes are below.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: 'Candidate HS codes are below.' },
            {
              type: 'table',
              title: 'Possible HS Codes',
              columns: [
                { key: 'hs_code', label: 'HS Code' },
                { key: 'description', label: 'Description' },
              ],
              rows: [
                { hs_code: '8471.30.00', description: 'Portable automatic data processing machines' },
                { hs_code: '8471.41.00', description: 'Other automatic data processing machines' },
              ],
            },
          ],
        },
      }),
    },
  ]);

  const tableCalls = calls.filter((call) => call.meta?.blocks?.some((block) => block.type === 'table'));
  const tableRows = tableCalls.map((call) => {
    const tableBlock = call.meta?.blocks?.find((block) => block.type === 'table');
    return tableBlock?.content.rows;
  });

  assert.deepEqual(tableRows, [[
    { hs_code: '8471.30.00', description: 'Portable automatic data processing machines' },
    { hs_code: '8471.41.00', description: 'Other automatic data processing machines' },
  ]]);
  assert.equal(tableCalls[0]?.meta?.blocks?.at(-1)?.isComplete, true);
  assert.equal(tableCalls.at(-1)?.meta?.status, 'completed');
});

test('streamFromChatApi preserves streamed text when final normalized payload has no content', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-empty-done', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'Hello' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-empty-done',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: '',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: '' },
          ],
        },
      }),
    },
  ]);

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.content, 'Hello');
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, 'Hello');
  assert.equal(finalCall.meta?.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.content, 'Hello');
  assert.equal(assistant.streamingContent, '');
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

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);

  assert.deepEqual(streamingCalls.map((call) => call.content).slice(0, 3), [
    'The ',
    'The HS c',
    'The HS code ',
  ]);
  assert.deepEqual(streamingCalls.map((call) => call.content).slice(-3), [
    'The HS code for a lap',
    'The HS code for a laptop is',
    'The HS code for a laptop is 8471.30...',
  ]);
  assert.deepEqual(streamingCalls.map((call) => call.meta?.streamingContent).slice(-3), [
    'The HS code for a lap',
    'The HS code for a laptop is',
    'The HS code for a laptop is 8471.30...',
  ]);
  assert.ok(streamingCalls.every((call) => call.meta?.blocks?.[0]?.type === 'markdown'));
  assert.equal(assistant.content, 'The HS code for a laptop is 8471.30.00.');
  assert.equal(assistant.streamingContent, '');
  assert.equal((assistant.normalizedResponse as Record<string, unknown>)?.request_id, 'request-delta-append');
});

test('streamFromChatApi streams genuine general answer and applies authoritative done', async () => {
  const answer = 'GDCE is Cambodia\'s General Department of Customs and Excise.';
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-general-stream', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'GDCE is ' } },
    { event: 'delta', data: { content: 'Cambodia\'s General Department ' } },
    { event: 'delta', data: { content: 'of Customs and Excise.' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-general-stream',
        service: 'general',
        intent: 'general',
        status: 'completed',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: answer,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: answer },
            {
              type: 'suggestions',
              items: ['What services does GDCE provide?'],
            },
          ],
        },
      }),
    },
  ], 'What is GDCE?');

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);

  assert.ok(streamingCalls.some((call) => call.content === 'GDCE is '));
  assert.ok(streamingCalls.some((call) => call.content.includes('Cambodia\'s General Department')));
  assert.ok(streamingCalls.at(-1)?.content.includes('of Customs and Excise.'));
  assert.ok(streamingCalls.every((call) => call.meta?.blocks?.[0]?.type === 'markdown'));
  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
  assert.deepEqual(assistant.blocks?.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(assistant.streamingContent, '');
  assert.equal(assistant.content, answer);
  assert.equal(assistant.blocks?.filter((block) => block.type === 'markdown').length, 1);
});

test('simple general response remains visible after real delta followed by done', async () => {
  const answer = 'Hello! How can I help you today?';
  const { assistant } = await streamWithReactiveAssistant([
    {
      event: 'start',
      data: {
        request_id: 'hello-test',
        service: 'general',
        intent: 'general',
        status: 'processing',
        mode: 'stream',
      },
    },
    {
      event: 'delta',
      data: {
        content: 'Hello! ',
      },
    },
    {
      event: 'delta',
      data: {
        content: 'How can I help you today?',
      },
    },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'hello-test',
        service: 'general',
        intent: 'general',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: answer,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            {
              type: 'markdown',
              text: answer,
            },
          ],
        },
      }),
    },
  ], 'Hello');

  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
  assert.equal(assistant.content, answer);
  assert.equal(assistant.blocks?.length, 1);
  assert.equal(assistant.blocks?.[0]?.type, 'markdown');
  assert.equal(assistant.blocks?.[0]?.content, answer);
  assert.equal(assistant.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.streamingContent, '');
});

test('streamFromChatApi allows legitimate general customs regulations prefix', async () => {
  const answer = 'Based on Cambodia Customs regulations, importers must provide supporting documents.';
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-general-prefix', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: answer } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-general-prefix',
        service: 'general',
        intent: 'general',
        status: 'completed',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: answer,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: answer },
          ],
        },
      }),
    },
  ], 'What documents do I need to import goods into Cambodia?');

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);

  assert.ok(streamingCalls.some((call) => call.content.includes('Based on Cambodia Customs regulations')));
  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
  assert.deepEqual(assistant.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(assistant.blocks?.some((block) => block.type === 'error'), false);
  assert.equal(assistant.content.includes('Response unavailable'), false);
  assert.equal(assistant.content, answer);
});

test('streamFromChatApi does not silently erase streamed text when done normalizes to empty content', async () => {
  const streamed = 'Hello! How can I help you today?';
  const { calls, assistant } = await streamWithReactiveAssistant([
    {
      event: 'start',
      data: {
        request_id: 'hello-empty-done',
        service: 'general',
        intent: 'general',
        status: 'processing',
        mode: 'stream',
      },
    },
    { event: 'delta', data: { content: 'Hello! ' } },
    { event: 'delta', data: { content: 'How can I help you today?' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'hello-empty-done',
        service: 'unknown',
        intent: 'general',
        status: 'completed',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: '',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: '' },
          ],
        },
      }),
    },
  ], 'Hello');

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.content, streamed);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content, streamed);
  assert.equal(finalCall.meta?.blocks?.[0]?.isComplete, true);
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.equal(assistant.content, streamed);
  assert.equal(assistant.blocks?.[0]?.content, streamed);
  assert.equal(assistant.blocks?.[0]?.isComplete, true);
  assert.equal(assistant.streamingContent, '');
});

test('streamFromChatApi does not apply calculator or trade draft suppression to explicit general streams', async () => {
  const answer = 'IMPORT TAX CALCULATION guidance can include a SUMMARY OF KEY FINDINGS section in training material.';
  const { calls, assistant } = await streamWithReactiveAssistant([
    {
      event: 'start',
      data: {
        request_id: 'request-general-routing',
        chat_id: 'chat-1',
        service: 'general',
        intent: 'general',
        status: 'processing',
      },
    },
    { event: 'delta', data: { content: 'IMPORT TAX CALCULATION guidance can include ' } },
    { event: 'delta', data: { content: 'a SUMMARY OF KEY FINDINGS section in training material.' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-general-routing',
        service: 'general',
        intent: 'general',
        status: 'completed',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: answer,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'markdown', text: answer },
          ],
        },
      }),
    },
  ], 'Explain customs training headings.');

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);

  assert.ok(streamingCalls.some((call) => call.content.includes('IMPORT TAX CALCULATION')));
  assert.ok(streamingCalls.some((call) => call.content.includes('SUMMARY OF KEY FINDINGS')));
  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
  assert.deepEqual(assistant.blocks?.map((block) => block.type), ['markdown']);
  assert.equal(assistant.content, answer);
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

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);
  const streamingCall = streamingCalls.at(-1);
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

test('streamFromChatApi clears processing state when a stream ends without final done payload', async () => {
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-missing-done', chat_id: 'chat-1', status: 'processing' } },
    { event: 'delta', data: { content: 'SUMMARY OF CALCULATION: temporary upstream text.' } },
  ]);

  const finalCall = calls.at(-1);

  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'error');
  assert.equal(finalCall.meta?.responseStatus, 'failed');
  assert.equal(finalCall.meta?.responseMode, 'stream');
  assert.equal(finalCall.meta?.progressStage, 'failed');
  assert.equal(finalCall.meta?.progressMessage, 'The response stream ended before the final response was received.');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['error']);
  assert.equal(assistant.status, 'error');
  assert.equal(assistant.responseStatus, 'failed');
  assert.equal(assistant.streamingContent, '');
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
  ], 'calculate import tax for hs code 8703.80.99 cif 40000USD from china');

  const streamingCalls = calls.filter((call) => call.meta?.progressStage === 'streaming' && call.content);
  const finalCall = calls.at(-1);

  assert.equal(calls[0]?.meta?.status, 'streaming');
  assert.equal(calls[0]?.meta?.responseStatus, 'processing');
  assert.equal(calls[0]?.meta?.requestId, 'request-calculator');
  assert.ok(streamingCalls.length > 0);
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

test('streamFromChatApi suppresses calculator report deltas before final normalized blocks', async () => {
  const draft = 'SUMMARY OF CALCULATION:The calculation determines the applicable duties and taxes for the imported goods.';
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-calculator-how-much', status: 'processing' } },
    { event: 'delta', data: { content: draft } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-calculator-how-much',
        service: 'calculator',
        intent: 'calculation',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: 'Import tax calculation complete.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            {
              type: 'summary',
              title: 'Import Tax Calculation',
              data: { total_tax: 0, currency: 'KHR' },
            },
          ],
        },
      }),
    },
  ], 'hi how much tax if i import a car hs 8703.22.00 cif is $10500, from china, ACFTA rate, dv=0');

  const rawStreamingCalls = calls.filter((call) => call.content.includes('SUMMARY OF CALCULATION'));
  const finalCall = calls.at(-1);

  assert.equal(rawStreamingCalls.length, 0);
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), ['summary']);
  assert.equal(finalCall.meta?.blocks?.[0]?.content?.data?.total_tax, 0);
  assert.equal(finalCall.content.includes('Import Tax Calculation'), true);
  assert.equal(finalCall.meta?.blocks?.some((block) => block.type === 'markdown' && block.content === draft), false);
});

test('streamFromChatApi suppresses realistic vehicle calculator report deltas', async () => {
  const rawCalculatorDraft = [
    'IMPORT TAX CALCULATION',
    '',
    'PRODUCT INFORMATION:',
    '* HS Code: 8703.22.00',
    '',
    'INPUT PARAMETERS:',
    '* CIF Value: 10,500 USD',
    '',
    'STEP 1: CURRENCY CONVERSION',
    '',
    'STEP 2: IMPORT TAX',
    '',
    'STEP 6: VEHICLE VALUATION FEE (VVF)',
    '',
    'FINAL TAX BREAKDOWN',
    '| Tax Component | Tax base (KHR) | Rate | Amount (KHR) |',
    '| COP | ... |',
    '',
    'SUMMARY:',
    'To import the vehicle...',
    '',
    'ASSUMPTIONS & NOTES:',
    '=== APPLICABLE RATES ===',
  ].join('\n');
  const { calls, assistant } = await streamWithReactiveAssistant([
    { event: 'start', data: { request_id: 'request-vehicle-calculator', status: 'processing' } },
    { event: 'delta', data: { content: rawCalculatorDraft } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-vehicle-calculator',
        service: 'calculator',
        intent: 'calculation',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Vehicle import tax calculation complete.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [
            { type: 'summary', title: 'Import Tax Calculation', data: { total_tax: 10314700, currency: 'KHR' } },
            { type: 'key_value', title: 'Product Information', items: [{ key: 'HS Code', value: '8703.22.00' }] },
            { type: 'key_value', title: 'Input Parameters', items: [{ key: 'CIF Value', value: '10,500 USD' }] },
            {
              type: 'table',
              title: 'Final Tax Breakdown',
              columns: [{ key: 'component', label: 'Tax Component' }],
              rows: [{ component: 'COP' }],
            },
            { type: 'details', title: 'Calculation Details', items: [{ title: 'STEP 1', content: 'Currency conversion' }] },
            { type: 'details', title: 'Assumptions & Notes', items: [{ title: 'Applicable Rates', content: 'Rates applied.' }] },
          ],
        },
      }),
    },
  ], 'calculate import tax for car hs 8703.22.00 cif 10500 usd from china');

  const rawStreamingCalls = calls.filter((call) =>
    call.content.includes('IMPORT TAX CALCULATION') ||
    call.content.includes('STEP 6: VEHICLE VALUATION FEE') ||
    call.content.includes('FINAL TAX BREAKDOWN')
  );
  const finalCall = calls.at(-1);

  assert.equal(rawStreamingCalls.length, 0);
  assert.ok(finalCall);
  assert.equal(finalCall.meta?.status, 'completed');
  assert.equal(finalCall.meta?.responseStatus, 'completed');
  assert.equal(finalCall.meta?.streamingContent, '');
  assert.deepEqual(finalCall.meta?.blocks?.map((block) => block.type), [
    'summary',
    'key_value',
    'key_value',
    'table',
    'details',
    'details',
  ]);
  assert.equal(finalCall.meta?.blocks?.some((block) => block.type === 'markdown' && String(block.content).includes('FINAL TAX BREAKDOWN')), false);
  assert.equal(assistant.streamingContent, '');
});

test('streamFromChatApi suppresses split calculator report heading deltas', async () => {
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-split-calculator-heading', status: 'processing' } },
    { event: 'delta', data: { content: 'FINAL TAX' } },
    { event: 'delta', data: { content: ' BREAKDOWN\n| Tax Component | Amount |' } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-split-calculator-heading',
        service: 'calculator',
        intent: 'calculation',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: 'Calculation complete.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [{ type: 'summary', title: 'Import Tax Calculation', data: { total_tax: 1 } }],
        },
      }),
    },
  ], 'calculate import tax');

  const rawStreamingCalls = calls.filter((call) => call.content.includes('FINAL TAX'));
  const finalCall = calls.at(-1);

  assert.equal(rawStreamingCalls.length, 0);
  assert.deepEqual(finalCall?.meta?.blocks?.map((block) => block.type), ['summary']);
});

test('streamFromChatApi still displays genuine concise calculator deltas', async () => {
  const conciseDelta = 'Your estimated import tax is 10,314,700 KHR.';
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-concise-calculator', status: 'processing' } },
    { event: 'delta', data: { content: conciseDelta } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-concise-calculator',
        service: 'calculator',
        intent: 'calculation',
        response: {
          type: 'markdown',
          coverage: 'complete',
          content: conciseDelta,
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [{ type: 'markdown', text: conciseDelta }],
        },
      }),
    },
  ], 'calculate import tax for car');

  assert.ok(calls.some((call) => call.content.includes(conciseDelta) && call.meta?.progressStage === 'streaming'));
  assert.equal(calls.at(-1)?.content, conciseDelta);
});

test('streamFromChatApi suppresses generic structured trade draft deltas', async () => {
  const draft = 'SUMMARY OF KEY FINDINGS: The provided trade data contains specific figures and insights.';
  const { calls } = await streamWithEvents([
    { event: 'start', data: { request_id: 'request-generic-draft', status: 'processing' } },
    { event: 'delta', data: { content: draft } },
    {
      event: 'done',
      data: normalizedResponse({
        request_id: 'request-generic-draft',
        service: 'trade',
        intent: 'trade_query',
        response: {
          type: 'markdown',
          coverage: 'unknown',
          content: 'Final structured trade response.',
          limitations: [],
        },
        message: {
          role: 'assistant',
          content: [{ type: 'markdown', text: 'Final structured trade response.' }],
        },
      }),
    },
  ], 'please check this');

  const streamingCallsWithDraft = calls.filter((call) => call.content.includes('SUMMARY OF KEY FINDINGS'));
  const finalCall = calls.at(-1);

  assert.equal(streamingCallsWithDraft.length, 0);
  assert.ok(finalCall);
  assert.equal(finalCall.content, 'Final structured trade response.');
  assert.equal(finalCall.meta?.blocks?.some((block) => block.type === 'markdown' && block.content === draft), false);
});

test('streamFromChatApi sends null backend ids for a brand-new normal chat', async () => {
  const { body } = await captureStreamRequestWithLocalState({});

  assert.equal(body.chat_id, null);
  assert.equal(body.project_id, null);
});

test('streamFromChatApi sends backend chat id for an existing normal chat', async () => {
  const backendChatId = '22222222-2222-4222-8222-222222222222';
  const { body } = await captureStreamRequestWithLocalState({ chatBackendId: backendChatId });

  assert.equal(body.chat_id, backendChatId);
  assert.equal(body.project_id, null);
});

test('streamFromChatApi sends backend project id and null chat id for a new project chat', async () => {
  const backendProjectId = '33333333-3333-4333-8333-333333333333';
  const { body, project } = await captureStreamRequestWithLocalState({
    includeProject: true,
    projectBackendId: backendProjectId,
  });

  assert.equal(body.chat_id, null);
  assert.equal(body.project_id, backendProjectId);
  assert.notEqual(body.project_id, project?.id);
});

test('streamFromChatApi sends backend chat and project ids for an existing project chat', async () => {
  const backendChatId = '44444444-4444-4444-8444-444444444444';
  const backendProjectId = '55555555-5555-4555-8555-555555555555';
  const { body } = await captureStreamRequestWithLocalState({
    includeProject: true,
    chatBackendId: backendChatId,
    projectBackendId: backendProjectId,
  });

  assert.equal(body.chat_id, backendChatId);
  assert.equal(body.project_id, backendProjectId);
});

test('streamFromChatApi stores backend chat id from SSE start event', async () => {
  const returnedBackendChatId = '66666666-6666-4666-8666-666666666666';
  const { chatStore, chat } = await captureStreamRequestWithLocalState({
    startChatId: returnedBackendChatId,
  });

  const storedChat = chatStore.recentChats.find((item) => item.id === chat.id);
  assert.equal(storedChat?.backendId, returnedBackendChatId);
});

test('streamFromChatApi synchronizes an old local project before project chat send', async () => {
  installRuntimeConfig();
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.accessToken = 'test-token';
  const chatStore = useChatStore();
  const projectStore = useProjectStore();
  const project = projectStore.addProject('Legacy Project', 'Local only');
  const chat = chatStore.createChat('New Chat', project.id);
  const backendProjectId = '77777777-7777-4777-8777-777777777777';
  const originalFetch = globalThis.fetch;
  const capturedBodies: Record<string, unknown>[] = [];

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    capturedBodies.push(JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>);
    if (url.endsWith('/api/v1/projects')) {
      return jsonResponse({ id: backendProjectId, name: project.name, description: project.description });
    }
    return sseResponse([
      { event: 'start', data: { request_id: 'request-1', chat_id: '88888888-8888-4888-8888-888888888888', project_id: backendProjectId } },
      { event: 'done', data: normalizedResponse() },
    ]);
  }) as typeof fetch;

  try {
    await useChatStreaming({
      chatId: chat.id,
      projectId: project.id,
      chatApi: {
        enabled: true,
        baseUrl: 'http://localhost:8000',
        apiToken: 'test-token',
        transport: 'gdce',
      },
      stopStreaming: { value: false },
      streamController: { value: null },
      currentRenderType: { value: 'idle' },
      typing: {
        config: {},
        sleep: async () => {},
        applyNaturalPause: async () => {},
        getPiecePause: () => 0,
      },
      upsertAssistantMessage: () => {},
      getAssistantMessage: () => null,
      getUiBlockDelay: () => 0,
    }).streamFromChatApi('hello', [], 'assistant-1');
  } finally {
    globalThis.fetch = originalFetch;
  }

  const chatRequestBody = capturedBodies.at(-1);
  assert.equal(chatRequestBody?.chat_id, null);
  assert.equal(chatRequestBody?.project_id, backendProjectId);
  assert.notEqual(chatRequestBody?.project_id, project.id);
  assert.equal(projectStore.projects.find((item) => item.id === project.id)?.backendId, backendProjectId);
});
