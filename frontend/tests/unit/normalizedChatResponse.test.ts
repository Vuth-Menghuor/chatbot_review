import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isNormalizedChatResponse,
  normalizedChatResponseToMessageParts,
} from '../../app/services/chat-api/normalizedChatResponse';
import type { NormalizedChatResponse } from '../../app/types/message';

const baseResponse: NormalizedChatResponse = {
  api_version: '1.0',
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
    { type: 'clarification', title: 'More information is needed', questions: ['Which origin country?'] },
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
    'clarification',
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

test('normalizedChatResponse maps trade clarification blocks to existing interactive fields', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    service: 'trade',
    intent: 'trade_query',
    status: 'clarification_required',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'More information is needed before querying trade data.',
      limitations: [],
    },
    clarifications: [
      'Which year should I use?',
      'Do you want imports, exports, or both?',
    ],
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'More information is needed before querying trade data.' },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: [
            'Which year should I use?',
            'Do you want imports, exports, or both?',
          ],
        },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.status, 'clarification_required');
  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'clarification']);
  assert.equal(parts.blocks[1].title, 'More information is needed');
  assert.deepEqual(parts.blocks[1].content.fields, [
    {
      name: 'clarification_1',
      label: 'Which year should I use?',
      type: 'text',
      required: true,
    },
    {
      name: 'clarification_2',
      label: 'Do you want imports, exports, or both?',
      type: 'text',
      required: true,
    },
  ]);
});

test('normalizedChatResponse renders calculator blocks from message content order only', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    service: 'general',
    intent: 'general',
    message: {
      role: 'assistant',
      content: [
        { type: 'summary', title: 'Import Tax Calculation', data: { total_tax: 572300 } },
        { type: 'key_value', title: 'Product Information', items: [{ key: 'HS Code', value: '0102.29.11' }] },
        { type: 'key_value', title: 'Input Parameters', items: [{ key: 'CIF Value', value: '800 USD' }] },
        {
          type: 'table',
          title: 'Tax Breakdown',
          columns: [{ key: 'amount', label: 'Amount' }],
          rows: [{ amount: 572300 }],
        },
        { type: 'details', title: 'Calculation Details', items: [{ title: 'Step 1', content: 'Convert currency' }] },
        { type: 'details', title: 'Assumptions & Notes', items: [{ title: 'Notes', content: 'Upstream note' }] },
        { type: 'references', title: 'References', items: [{ title: 'Customs Tariff' }] },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), [
    'summary',
    'key_value',
    'key_value',
    'table',
    'details',
    'details',
    'references',
  ]);
  assert.equal(parts.content, response.response?.content);
  assert.equal(parts.blocks.some((block) => block.type === 'markdown'), false);
  assert.deepEqual(parts.blocks.map((block) => block.title), [
    'Import Tax Calculation',
    'Product Information',
    'Input Parameters',
    'Tax Breakdown',
    'Calculation Details',
    'Assumptions & Notes',
    'References',
  ]);
});

test('normalizedChatResponse falls back to response content only when message blocks are empty', () => {
  const response = responseWithBlocks([]);

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown']);
  assert.equal(parts.blocks[0].content, 'Calculator answer.');
  assert.equal(parts.content, 'Calculator answer.');
});

test('normalized trade response keeps response content as fallback without duplicating visual markdown', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    service: 'trade',
    intent: 'trade_query',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'Trade answer.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Trade answer.' },
        {
          type: 'table',
          title: 'Trade Table',
          columns: [{ key: 'partner', label: 'Partner' }],
          rows: [{ partner: 'Vietnam' }],
        },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.content, 'Trade answer.');
  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'table']);
  assert.equal(parts.blocks.filter((block) => block.type === 'markdown').length, 1);
  assert.equal(parts.blocks[0].content, 'Trade answer.');
});

test('normalized trade response maps supported block types through generic renderable message blocks', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    service: 'trade',
    intent: 'trade_query',
    status: 'partial',
    response: {
      type: 'markdown',
      coverage: 'partial',
      content: 'Trade results are available.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Trade results are available.' },
        {
          type: 'summary',
          title: 'Trade Data Summary',
          data: { currency: 'USD', total_trade_value: 2100000 },
        },
        {
          type: 'table',
          title: 'Top Export Partners',
          columns: [
            { key: 'partner_country', label: 'Partner Country' },
            { key: 'value_usd', label: 'Value USD' },
          ],
          rows: [{ partner_country: 'Vietnam', value_usd: 1200000 }],
        },
        {
          type: 'chart',
          title: 'Exports by Partner',
          data: {
            chartType: 'bar',
            data: [{ label: 'Vietnam', value_usd: 1200000 }],
            series: [{ key: 'value_usd', name: 'Value USD', type: 'bar' }],
          },
        },
        {
          type: 'coverage',
          title: 'Data availability',
          tone: 'warning',
          items: ['The 2026 data is not complete yet.'],
        },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: ['Which year should I use?'],
        },
        {
          type: 'suggestions',
          title: 'Related questions',
          items: ['Compare exports with imports'],
        },
        { type: 'error', message: 'The trade data request timed out.' },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), [
    'markdown',
    'summary',
    'table',
    'chart',
    'coverage',
    'clarification',
    'suggestions',
    'error',
  ]);
  assert.equal(parts.blocks[1].content.title, 'Trade Data Summary');
  assert.equal(parts.blocks[1].content.data.total_trade_value, 2100000);
  assert.equal(parts.blocks[2].content.rows[0].partner_country, 'Vietnam');
  assert.equal(parts.blocks[3].content.chartType, 'bar');
  assert.deepEqual(parts.blocks[4].content.items, ['The 2026 data is not complete yet.']);
  assert.equal(parts.blocks[5].content.kind, 'form');
  assert.equal(parts.blocks[5].content.fields[0].label, 'Which year should I use?');
  assert.deepEqual(parts.blocks[6].content, ['Compare exports with imports']);
  assert.equal(parts.blocks[7].content.message, 'The trade data request timed out.');
});

test('normalized trade response maps unknown future blocks to fallback without service-specific handling', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    service: 'trade',
    intent: 'trade_query',
    message: {
      role: 'assistant',
      content: [
        { type: 'future_trade_block', data: { value: 1 } },
      ] as NormalizedChatResponse['message']['content'],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['fallback']);
  assert.equal(parts.blocks[0].content, 'Unsupported response content');
});

test('normalized trade response preserves original numeric units currencies percentages periods and rank ordering', () => {
  const response: NormalizedChatResponse = {
    ...baseResponse,
    service: 'trade',
    intent: 'trade_query',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'Trade values are available.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        {
          type: 'summary',
          title: 'Trade Data Summary',
          data: {
            currency: 'USD',
            total_trade_value: 1200000,
            total_weight_kg: 4500,
            growth_rate_pct: 7.25,
            period: 2024,
          },
        },
        {
          type: 'table',
          title: 'Top Export Partners',
          columns: [
            { key: 'rank', label: 'Rank' },
            { key: 'partner_country', label: 'Partner Country' },
            { key: 'value_usd', label: 'Value USD' },
            { key: 'weight_kg', label: 'Weight KG' },
            { key: 'share_percent', label: 'Share Percent' },
            { key: 'period', label: 'Period' },
          ],
          rows: [
            {
              rank: 1,
              partner_country: 'Vietnam',
              value_usd: 1200000,
              weight_kg: 4500,
              share_percent: 24.5,
              period: 2024,
            },
            {
              rank: 2,
              partner_country: 'Thailand',
              value_usd: 900000,
              weight_kg: 3000,
              share_percent: 18,
              period: 2024,
            },
          ],
        },
        {
          type: 'chart',
          title: 'Exports by Partner',
          data: {
            chartType: 'bar',
            yLabel: 'Value USD',
            data: [
              { label: 'Vietnam', value_usd: 1200000 },
              { label: 'Thailand', value_usd: 900000 },
            ],
            series: [{ key: 'value_usd', name: 'Value USD', type: 'bar' }],
          },
        },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');
  const summary = parts.blocks[0].content.data;
  const tableRows = parts.blocks[1].content.rows;
  const chart = parts.blocks[2].content;

  assert.equal(summary.currency, 'USD');
  assert.equal(summary.total_trade_value, 1200000);
  assert.equal(summary.total_weight_kg, 4500);
  assert.equal(summary.growth_rate_pct, 7.25);
  assert.equal(summary.period, 2024);
  assert.deepEqual(tableRows.map((row) => row.rank), [1, 2]);
  assert.deepEqual(tableRows.map((row) => row.partner_country), ['Vietnam', 'Thailand']);
  assert.deepEqual(tableRows.map((row) => row.value_usd), [1200000, 900000]);
  assert.deepEqual(tableRows.map((row) => row.weight_kg), [4500, 3000]);
  assert.deepEqual(tableRows.map((row) => row.share_percent), [24.5, 18]);
  assert.deepEqual(tableRows.map((row) => row.period), [2024, 2024]);
  assert.equal(chart.yLabel, 'Value USD');
  assert.deepEqual(chart.data.map((row) => row.value_usd), [1200000, 900000]);
  assert.deepEqual(chart.data.map((row) => row.label), ['Vietnam', 'Thailand']);
});

test('normalizedChatResponse rejects legacy message.blocks aliases for normalized v1 envelopes', () => {
  const response = {
    ...baseResponse,
    message: {
      role: 'assistant',
      text: 'Alias text.',
      blocks: [{ type: 'markdown', text: 'Alias markdown.' }],
    },
  };

  assert.equal(isNormalizedChatResponse(response), false);
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

test('normalizedChatResponse rejects envelopes without message content arrays', () => {
  assert.equal(isNormalizedChatResponse({ ...baseResponse, message: { role: 'assistant' } }), false);
  assert.equal(isNormalizedChatResponse({ ...baseResponse, message: { role: 'assistant', blocks: [] } }), false);
  assert.equal(isNormalizedChatResponse({ ...baseResponse, message: { role: 'assistant', content: [] } }), true);
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
      content: [
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

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'clarification', 'suggestions']);
  assert.equal(parts.blocks[1].title, 'More information is needed');
  assert.deepEqual(parts.blocks[1].content.fields.map((field) => field.label), [
    'Are you asking about import or export?',
    'Which product should I use?',
  ]);
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
      content: [{ type: 'error', message: 'The general service is temporarily unavailable.' }],
    },
    citations: [],
  };

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.status, 'failed');
  assert.equal(parts.blocks[0].type, 'error');
  assert.equal(parts.blocks[0].content.message, 'The general service is temporarily unavailable.');
});

test('normalizedChatResponse keeps malformed general-style blocks from crashing', () => {
  const response = {
    ...baseResponse,
    request_id: 'general-malformed-contract',
    service: 'general',
    intent: 'general',
    message: {
      role: 'assistant',
      content: [
        { type: 'suggestions', title: 'Suggested follow-ups', items: 'not-an-array' },
        { type: 'clarification', title: 'More information is needed', questions: 'not-an-array' },
        { type: 'future_general_block', value: 'new shape' },
      ],
    },
  };

  const parts = normalizedChatResponseToMessageParts(response as NormalizedChatResponse, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['suggestions', 'clarification', 'fallback']);
  assert.deepEqual(parts.blocks[0].content, []);
  assert.deepEqual(parts.blocks[1].content.fields, []);
});
