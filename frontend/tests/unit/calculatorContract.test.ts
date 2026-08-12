import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  handleNormalizedChatResponse,
  isNormalizedChatResponse,
  normalizedChatResponseToMessageParts,
} from '../../app/services/chat-api/normalizedChatResponse';
import { parseNormalizedChatResponse } from '../../app/services/chat-api/normalizedChatResponseSchema';
import type { NormalizedChatResponse } from '../../app/types/message';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixturePath = resolve(__dirname, '../fixtures/normalized-calculator-petroleum-response.json');

function loadPetroleumFixture(): NormalizedChatResponse {
  return JSON.parse(readFileSync(fixturePath, 'utf8')) as NormalizedChatResponse;
}

function withBlocks(blocks: unknown[]): NormalizedChatResponse {
  const fixture = loadPetroleumFixture();
  return {
    ...fixture,
    message: {
      role: 'assistant',
      content: blocks as NormalizedChatResponse['message']['content'],
    },
  };
}

test('calculator summary block renders from the normalized petroleum fixture', () => {
  const parts = normalizedChatResponseToMessageParts(loadPetroleumFixture(), 'fallback-id');
  const summary = parts.blocks[0];

  assert.equal(summary.type, 'summary');
  assert.equal(summary.title, 'Import Tax Calculation');
  assert.equal(summary.content.data.total_tax, 2500000);
  assert.equal(summary.content.data.currency, 'KHR');
  assert.equal(summary.content.data.phase_gap, '100,000 KHR');
});

test('calculator key-value blocks render product and input parameters', () => {
  const parts = normalizedChatResponseToMessageParts(loadPetroleumFixture(), 'fallback-id');
  const [product, inputs] = parts.blocks.filter((block) => block.type === 'key_value');

  assert.equal(product.title, 'Product Information');
  assert.deepEqual(product.content.items, [
    { key: 'hs_code', value: '2710.12.21' },
    { key: 'description', value: 'Petroleum' },
  ]);
  assert.equal(inputs.title, 'Input Parameters');
  assert.deepEqual(inputs.content.items, [
    { key: 'declared_value', value: '500 USD/MT' },
    { key: 'quantity', value: '10 MT' },
  ]);
});

test('calculator tax table renders columns and rows without changing values', () => {
  const parts = normalizedChatResponseToMessageParts(loadPetroleumFixture(), 'fallback-id');
  const table = parts.blocks.find((block) => block.type === 'table');

  assert.ok(table);
  assert.equal(table.title, 'Tax Breakdown');
  assert.deepEqual(table.content.columns.map((column) => column.key), [
    'component',
    'tax_base',
    'rate',
    'amount',
    'currency',
  ]);
  assert.deepEqual(table.content.rows, [
    { component: 'Phase 1', tax_base: 'DV', rate: '35%', amount: 1200000, currency: 'KHR' },
    { component: 'Phase 2', tax_base: 'State charge', rate: '10%', amount: 1300000, currency: 'KHR' },
  ]);
});

test('calculator details blocks render calculation details and assumptions', () => {
  const parts = normalizedChatResponseToMessageParts(loadPetroleumFixture(), 'fallback-id');
  const [calculation, assumptions] = parts.blocks.filter((block) => block.type === 'details');

  assert.equal(calculation.title, 'Calculation Details');
  assert.equal(calculation.content.items[0].title, 'Phase 1');
  assert.equal(calculation.content.items[0].content.includes('basis: Declared value'), true);
  assert.equal(calculation.content.items[0].content.includes('component: CPP'), true);
  assert.equal(assumptions.title, 'Assumptions & Notes');
  assert.equal(assumptions.content.items[1].content, 'Importer pays Phase 1 amount.');
});

test('calculator markdown fallback renders when no structured blocks are present', () => {
  const response = withBlocks([]);
  response.response.content = 'Plain calculator answer.';

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown']);
  assert.equal(parts.blocks[0].content, 'Plain calculator answer.');
});

test('calculator error block renders failed responses', () => {
  const response = withBlocks([{ type: 'error', message: 'Calculator service is unavailable' }]);
  response.status = 'failed';
  response.response.content = '';

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.status, 'failed');
  assert.deepEqual(parts.blocks.map((block) => block.type), ['error']);
  assert.equal(parts.blocks[0].content.message, 'Calculator service is unavailable');
});

test('calculator clarification block renders questions as form fields', () => {
  const response = withBlocks([
    {
      type: 'clarification',
      title: 'More information is needed',
      questions: ['What is the CIF value?', 'What is the origin country?'],
    },
  ]);

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['clarification']);
  assert.deepEqual(parts.blocks[0].content.fields.map((field) => field.label), [
    'What is the CIF value?',
    'What is the origin country?',
  ]);
});

test('unknown calculator block types use the safe fallback renderer', () => {
  const response = withBlocks([{ type: 'future_calculator_block', value: 'new shape' }]);

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['fallback']);
  assert.equal(parts.blocks[0].content, 'Unsupported response content');
});

test('calculator blocks do not duplicate the full plain-text answer', () => {
  const response = loadPetroleumFixture();

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.content, response.response.content);
  assert.equal(parts.blocks.some((block) => block.type === 'markdown' && block.content === response.response.content), false);
});

test('empty calculator block array falls back to response content', () => {
  const response = withBlocks([]);

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown']);
  assert.equal(parts.blocks[0].content, response.response.content);
});

test('invalid normalized calculator response validation returns a stable error', () => {
  const invalid = {
    ...loadPetroleumFixture(),
    request_id: 12345,
    message: { role: 'assistant', content: [] },
  };

  assert.equal(isNormalizedChatResponse(invalid), false);
  assert.equal(parseNormalizedChatResponse(invalid), null);

  const parts = handleNormalizedChatResponse(invalid, 'invalid-calculator');

  assert.ok(parts);
  assert.equal(parts.status, 'failed');
  assert.deepEqual(parts.blocks.map((block) => block.type), ['error']);
  assert.equal(parts.blocks[0].content.message, 'The response format was not supported.');
});
