import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isNormalizedChatResponse,
  normalizedChatResponseToMessageParts,
} from '../../app/services/chat-api/normalizedChatResponse';
import type { NormalizedChatResponse } from '../../app/types/message';

const baseResponse: NormalizedChatResponse = {
  request_id: 'frontend-contract',
  session_id: 'session-1',
  status: 'completed',
  service: 'calculator',
  intent: 'calculator',
  coverage: 'complete',
  confidence: 'high',
  response: {
    type: 'markdown',
    coverage: 'complete',
    confidence: 'high',
    content: 'Calculator answer.',
    limitations: [],
  },
  message: {
    role: 'assistant',
    content: [],
  },
  citations: [],
  suggestions: [],
  metrics: { latency_ms: 25 },
};

function responseWithBlocks(blocks: unknown[]): NormalizedChatResponse {
  return {
    ...baseResponse,
    message: {
      role: 'assistant',
      content: blocks as NormalizedChatResponse['message']['content'],
    },
  };
}

test('normalizedChatResponse maps all supported API block types', () => {
  const response = responseWithBlocks([
    { type: 'summary', title: 'Summary', data: { total_tax: 572300 } },
    { type: 'key_value', title: 'Product', items: [{ key: 'HS Code', value: '0102.29.11' }] },
    {
      type: 'table',
      title: 'Tax Breakdown',
      columns: [{ key: 'amount', label: 'Amount' }],
      rows: [{ amount: 572300 }],
    },
    { type: 'details', title: 'Calculation Details', items: [{ title: 'Step 1', content: 'Convert currency' }] },
    { type: 'references', title: 'References', items: [{ title: 'Customs Tariff' }] },
    { type: 'suggestions', title: 'Suggested follow-ups', items: ['Explain VAT'] },
    { type: 'markdown', text: 'Plain markdown.' },
    { type: 'chart', title: 'Trade Chart', data: { chartType: 'bar', data: [{ label: 'A', value: 1 }] } },
    { type: 'error', message: 'Request failed upstream' },
  ]);

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), [
    'summary',
    'key_value',
    'table',
    'details',
    'references',
    'suggestions',
    'markdown',
    'chart',
    'error',
  ]);
  assert.equal(parts.status, 'completed');
  assert.equal(parts.coverage, 'complete');
  assert.equal(parts.confidence, 'high');
  assert.equal(parts.latencyMs, 25);
});

test('normalizedChatResponse accepts message.blocks and message.text aliases', () => {
  const response = {
    ...baseResponse,
    message: {
      role: 'assistant',
      text: 'Alias text.',
      blocks: [{ type: 'markdown', text: 'Alias markdown.' }],
    },
  };

  assert.equal(isNormalizedChatResponse(response), true);

  const parts = normalizedChatResponseToMessageParts(response as NormalizedChatResponse, 'fallback-id');

  assert.equal(parts.blocks[0].type, 'markdown');
  assert.equal(parts.blocks[0].content, 'Alias markdown.');
});

test('normalizedChatResponse turns unknown and malformed blocks into fallback blocks', () => {
  const response = responseWithBlocks([
    { type: 'future_block', payload: { value: 1 } },
    null,
    { type: 'table', title: 'Malformed Table' },
    { type: 'error' },
  ]);

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['fallback', 'fallback', 'table', 'error']);
  assert.equal(parts.blocks[2].content.rows.length, 0);
  assert.equal(parts.blocks[3].content.message, 'Request failed');
});

test('normalizedChatResponse rejects envelopes without block arrays', () => {
  assert.equal(isNormalizedChatResponse({ ...baseResponse, message: { role: 'assistant' } }), false);
  assert.equal(isNormalizedChatResponse({ ...baseResponse, message: { role: 'assistant', blocks: [] } }), true);
});

test('normalizedChatResponse maps retrieval markdown, coverage, and citations safely', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    request_id: 'retrieval-contract',
    service: 'retrieval',
    intent: 'retrieval',
    coverage: 'partial',
    response: {
      type: 'markdown',
      coverage: 'partial',
      content: 'Retrieval answer.',
      limitations: [{ code: 'MISSING_DETAIL', message: 'Some details were not found.' }],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Retrieval answer.' },
        {
          type: 'coverage',
          title: 'Information limitation',
          tone: 'warning',
          items: ['Some details were not found.'],
          note: 'The available sources do not provide every requested detail.',
        },
      ],
    },
    citations: [
      {
        id: 'doc-1',
        title: 'Import Declaration Guidance',
        url: 'https://example.test/import-declaration',
        snippet: 'Import declaration requirements.',
        citation_id: 'doc-1',
        document_id: 'import-guidance',
        filename: 'import-guidance.pdf',
        chunk_index: 2,
        retrieval_method: 'semantic',
      },
    ],
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'coverage']);
  assert.equal(parts.blocks[1].content.tone, 'warning');
  assert.equal(parts.sources[0].title, 'Import Declaration Guidance');
  assert.equal(parts.sources[0].domain, 'example.test');
  assert.equal(parts.sources[0].documentId, 'import-guidance');
  assert.equal(parts.sources[0].chunkIndex, 2);
});

test('normalizedChatResponse keeps malformed retrieval-style blocks from crashing', () => {
  const response = {
    ...baseResponse,
    request_id: 'retrieval-malformed-contract',
    service: 'retrieval',
    intent: 'retrieval',
    message: {
      role: 'assistant',
      blocks: [
        { type: 'coverage', title: 'Missing Trade Data', items: 'not-an-array' },
        { type: 'chart', title: 'Malformed Chart', data: null },
        { type: 'future_retrieval_block', rows: [{ value: 1 }] },
      ],
    },
  };

  assert.equal(isNormalizedChatResponse(response), true);

  const parts = normalizedChatResponseToMessageParts(response as NormalizedChatResponse, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['coverage', 'chart', 'fallback']);
  assert.deepEqual(parts.blocks[0].content.items, []);
  assert.deepEqual(parts.blocks[1].content.output, {});
});

test('normalizedChatResponse maps general suggestions and clarification blocks', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    request_id: 'general-contract',
    service: 'general',
    intent: 'general',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'I need a little more information.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'I need a little more information.' },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: ['Are you asking about import or export?', 'Which product should I use?'],
        },
        {
          type: 'suggestions',
          title: 'Suggested follow-ups',
          items: ['Ask about import documents', 'Calculate import tax'],
        },
      ],
    },
    citations: [],
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'markdown', 'suggestions']);
  assert.equal(parts.blocks[1].title, 'More information is needed');
  assert.match(parts.blocks[1].content, /Are you asking about import or export/);
  assert.deepEqual(parts.blocks[2].content, ['Ask about import documents', 'Calculate import tax']);
});

test('normalizedChatResponse maps failed general responses to error blocks', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    request_id: 'general-failed-contract',
    service: 'general',
    intent: 'general',
    status: 'failed',
    coverage: 'unknown',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: '',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [{ type: 'error', message: 'General service is unavailable' }],
    },
    citations: [],
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.status, 'failed');
  assert.equal(parts.blocks[0].type, 'error');
  assert.equal(parts.blocks[0].content.message, 'General service is unavailable');
});

test('normalizedChatResponse keeps malformed general-style blocks from crashing', () => {
  const response = {
    ...baseResponse,
    request_id: 'general-malformed-contract',
    service: 'general',
    intent: 'general',
    message: {
      role: 'assistant',
      blocks: [
        { type: 'suggestions', title: 'Suggested follow-ups', items: 'not-an-array' },
        { type: 'clarification', title: 'More information is needed', questions: 'not-an-array' },
        { type: 'future_general_block', value: 'new shape' },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response as NormalizedChatResponse, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['suggestions', 'markdown', 'fallback']);
  assert.deepEqual(parts.blocks[0].content, []);
  assert.equal(parts.blocks[1].content, '**More information is needed**\n\n');
});
