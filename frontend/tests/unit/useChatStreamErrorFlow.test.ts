import test from 'node:test';
import assert from 'node:assert/strict';
import { setActivePinia, createPinia } from 'pinia';

import { useChat } from '../../app/composables';
import { useAuthStore } from '../../app/stores/auth.store';

type FetchMock = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function installRuntimeConfig() {
  const globalWithNuxt = globalThis as typeof globalThis & {
    useRuntimeConfig?: () => Record<string, unknown>;
  };
  globalWithNuxt.useRuntimeConfig = () => ({
    public: {
      gdceApiEnabled: true,
      gdceApiBaseUrl: 'http://localhost:8000',
      allowedImageTypes: 'image/jpeg,image/png,image/webp',
      maxImageSizeMb: 5,
    },
  });
}

function setupChat(fetchMock: FetchMock) {
  installRuntimeConfig();
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.accessToken = 'test-token';

  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock as typeof fetch;

  return {
    chat: useChat(),
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

function sseDoneResponse(payload: unknown) {
  return new Response(`event: start\ndata: {"request_id":"request-1"}\n\nevent: done\ndata: ${JSON.stringify(payload)}\n\n`, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

async function sendWithFetch(fetchMock: FetchMock) {
  const { chat, restore } = setupChat(fetchMock);
  try {
    await chat.send('What documents do I need?');
    return chat;
  } finally {
    restore();
  }
}

function assertFriendlyErrorState(chat: ReturnType<typeof useChat>, forbiddenText?: string) {
  assert.equal(chat.loading.value, false);
  assert.equal(chat.currentRenderType.value, 'idle');
  assert.equal(chat.messages.value[0]?.role, 'user');
  assert.equal(chat.messages.value[0]?.content, 'What documents do I need?');

  const assistant = chat.messages.value[1];
  assert.ok(assistant);
  assert.equal(assistant.role, 'assistant');
  assert.equal(assistant.status, 'error');
  assert.equal(assistant.responseStatus, 'failed');
  assert.deepEqual(assistant.blocks?.map((block) => block.type), ['error']);
  assert.equal(typeof assistant.blocks?.[0]?.content, 'object');
  if (forbiddenText) {
    assert.equal(assistant.content.includes(forbiddenText), false);
    assert.equal(JSON.stringify(assistant.blocks?.[0]?.content).includes(forbiddenText), false);
  }
}

test('useChat renders a friendly error block for 401 authentication failures', async () => {
  const chat = await sendWithFetch(async () => new Response('{"detail":"token expired stack trace"}', { status: 401 }));

  assertFriendlyErrorState(chat, 'stack trace');
  assert.match(chat.messages.value[1]?.content ?? '', /session has expired/i);
});

test('useChat renders a friendly error block for 503 orchestrator unavailable', async () => {
  const chat = await sendWithFetch(async () => new Response('orchestrator traceback unavailable', { status: 503 }));

  assertFriendlyErrorState(chat, 'traceback');
  assert.match(chat.messages.value[1]?.content ?? '', /temporarily unavailable/i);
});

test('useChat renders a friendly error block for network interruption', async () => {
  const chat = await sendWithFetch(async () => {
    throw new TypeError('fetch failed: ECONNRESET internal-host.local');
  });

  assertFriendlyErrorState(chat, 'internal-host.local');
  assert.match(chat.messages.value[1]?.content ?? '', /could not reach/i);
});

test('useChat renders safe ErrorRenderer payloads for invalid normalized done payloads', async () => {
  const chat = await sendWithFetch(async () => sseDoneResponse({
    api_version: '1.0',
    answer: 'This invalid versioned payload must not render as markdown.',
  }));

  assert.equal(chat.loading.value, false);
  assert.equal(chat.currentRenderType.value, 'idle');
  assert.equal(chat.messages.value[0]?.role, 'user');
  const assistant = chat.messages.value[1];
  assert.ok(assistant);
  assert.equal(assistant.status, 'error');
  assert.equal(assistant.responseStatus, 'failed');
  assert.deepEqual(assistant.blocks?.map((block) => block.type), ['error']);
  assert.equal(assistant.content.includes('This invalid versioned payload'), false);
});

test('useChat treats user abort as cancellation without a false failure', async () => {
  installRuntimeConfig();
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.accessToken = 'test-token';

  const originalFetch = globalThis.fetch;
  let markFetchStarted: (() => void) | null = null;
  const fetchStarted = new Promise<void>((resolve) => {
    markFetchStarted = resolve;
  });
  globalThis.fetch = (async (_input, init) => new Promise<Response>((_resolve, reject) => {
    markFetchStarted?.();
    init?.signal?.addEventListener('abort', () => {
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    }, { once: true });
  })) as typeof fetch;

  const chat = useChat();
  try {
    const sendPromise = chat.send('What documents do I need?');
    await fetchStarted;
    chat.stop();
    await sendPromise;
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(chat.loading.value, false);
  assert.equal(chat.currentRenderType.value, 'idle');
  assert.equal(chat.messages.value[0]?.role, 'user');
  assert.equal(chat.messages.value[0]?.content, 'What documents do I need?');
  const assistant = chat.messages.value[1];
  assert.ok(assistant);
  assert.equal(assistant.status, 'stopped');
  assert.equal(Boolean(assistant.blocks?.some((block) => block.type === 'error')), false);
});
