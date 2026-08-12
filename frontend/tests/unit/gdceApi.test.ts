import test from 'node:test';
import assert from 'node:assert/strict';

import { streamGdceChat } from '../../app/services/chat-api/gdceApi';
import { presentationPreferenceFromMessage } from '../../app/composables/chat/useChatStreaming';

function sseResponse() {
  return new Response('event: done\ndata: {"status":"completed"}\n\n', {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

async function captureStreamBody(options: {
  chatId?: string;
  projectId?: string;
  message?: string;
  presentation?: {
    preferred_blocks: string[];
    fallback: 'markdown';
  };
  context?: Record<string, unknown>;
}) {
  let captured: Record<string, unknown> | null = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    captured = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
    return sseResponse();
  }) as typeof fetch;

  try {
    await streamGdceChat({
      baseUrl: 'http://localhost:8000',
      apiToken: 'test-token',
      message: options.message ?? 'What documents do I need?',
      chatId: options.chatId,
      projectId: options.projectId,
      presentation: options.presentation,
      context: options.context,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.notEqual(captured, null);
  return captured!;
}

test('streamGdceChat sends null project_id for normal chat', async () => {
  const body = await captureStreamBody({});

  assert.equal(body.chat_id, null);
  assert.equal(body.project_id, null);
  assert.equal(body.message, 'What documents do I need?');
  assert.deepEqual(body.attachments, []);
  assert.deepEqual(body.metadata, { client: 'gdce-nuxt-frontend' });
  assert.equal('presentation' in body, false);
});

test('streamGdceChat forwards active project UUID for project chat', async () => {
  const projectId = '7e00f73c-2f0f-4f45-aea9-9a0f94ed15f4';
  const body = await captureStreamBody({ projectId });

  assert.equal(body.chat_id, null);
  assert.equal(body.project_id, projectId);
});

test('streamGdceChat forwards chat_id and project_id for existing project chat', async () => {
  const chatId = 'fbf669d4-5e82-4111-9257-818f18cb54d5';
  const projectId = '7e00f73c-2f0f-4f45-aea9-9a0f94ed15f4';
  const body = await captureStreamBody({ chatId, projectId });

  assert.equal(body.chat_id, chatId);
  assert.equal(body.project_id, projectId);
});

test('streamGdceChat forwards presentation preference without modifying message text', async () => {
  const message = 'Give me the HS code for cotton fabric as a table.';
  const presentation = {
    preferred_blocks: ['table'],
    fallback: 'markdown' as const,
  };
  const body = await captureStreamBody({ message, presentation });

  assert.equal(body.message, message);
  assert.deepEqual(body.presentation, presentation);
});

test('streamGdceChat can forward chart presentation preference', async () => {
  const message = 'Show import data as a chart.';
  const presentation = {
    preferred_blocks: ['chart'],
    fallback: 'markdown' as const,
  };
  const body = await captureStreamBody({ message, presentation });

  assert.equal(body.message, message);
  assert.deepEqual(body.presentation, presentation);
});

test('streamGdceChat forwards clarification context with same chat request', async () => {
  const chatId = 'fbf669d4-5e82-4111-9257-818f18cb54d5';
  const message = 'The fabric is 100% cotton, dyed, and weighs 180 g/m².';
  const context = {
    reply_to_request_id: 'cf827455-bd51-4424-a944-a3a3582244b7',
  };
  const body = await captureStreamBody({ chatId, message, context });

  assert.equal(body.chat_id, chatId);
  assert.equal(body.message, message);
  assert.deepEqual(body.context, context);
});

test('presentationPreferenceFromMessage detects explicit output format requests only', () => {
  assert.deepEqual(presentationPreferenceFromMessage('Give me the HS code as a table.'), {
    preferred_blocks: ['table'],
    fallback: 'markdown',
  });
  assert.deepEqual(presentationPreferenceFromMessage('Show the previous result as a table.'), {
    preferred_blocks: ['table'],
    fallback: 'markdown',
  });
  assert.deepEqual(presentationPreferenceFromMessage('Show import data as a chart.'), {
    preferred_blocks: ['chart'],
    fallback: 'markdown',
  });
  assert.deepEqual(presentationPreferenceFromMessage('Show the result as a card.'), {
    preferred_blocks: ['prediction'],
    fallback: 'markdown',
  });
  assert.deepEqual(presentationPreferenceFromMessage('Generate a report.'), {
    preferred_blocks: ['report'],
    fallback: 'markdown',
  });
  assert.equal(presentationPreferenceFromMessage('What is the HS code for cotton fabric?'), undefined);
});
