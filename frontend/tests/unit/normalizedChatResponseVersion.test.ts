import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  handleNormalizedChatResponse,
  isNormalizedChatResponse,
  normalizedChatResponseToMessageParts,
} from '../../app/services/chat-api/normalizedChatResponse';
import { parseNormalizedChatResponse } from '../../app/services/chat-api/normalizedChatResponseSchema';
import type { NormalizedChatResponse } from '../../app/types/message';

const fixtureDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');

function readFixture(name: string): unknown {
  return JSON.parse(readFileSync(join(fixtureDir, name), 'utf8'));
}

function baseGeneralResponse(overrides: Partial<NormalizedChatResponse> = {}): NormalizedChatResponse {
  const base = readFixture('normalized-general-response.json') as NormalizedChatResponse;
  return {
    ...base,
    ...overrides,
    response: overrides.response ?? base.response,
    message: overrides.message ?? base.message,
    citations: overrides.citations ?? base.citations,
    suggestions: overrides.suggestions ?? base.suggestions,
    metrics: overrides.metrics ?? base.metrics,
  };
}

test('normalized chat response requires api_version 1.0', () => {
  const response = readFixture('normalized-general-response.json');

  assert.equal(isNormalizedChatResponse(response), true);
  assert.equal((response as NormalizedChatResponse).api_version, '1.0');
});

test('normalized chat response rejects missing or unsupported api_version', () => {
  const response = readFixture('normalized-general-response.json') as Record<string, unknown>;

  const withoutVersion = { ...response };
  delete withoutVersion.api_version;

  assert.equal(isNormalizedChatResponse(withoutVersion), false);
  assert.equal(isNormalizedChatResponse({ ...response, api_version: '2.0' }), false);
});

test('versioned normalized response still maps to frontend message parts', () => {
  const response = readFixture('normalized-general-response.json') as NormalizedChatResponse;

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.status, 'completed');
  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(parts.latencyMs, 125);
});

test('successful general response preserves markdown, status, latency, and has no duplicate answer block', () => {
  const response = baseGeneralResponse();

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(parts!.blocks[0].content, response.response?.content);
  assert.equal(parts!.blocks.filter((block) => block.type === 'markdown').length, 1);
  assert.equal(parts!.status, 'completed');
  assert.equal(parts!.latencyMs, 125);
});

test('customs service fallback is shown as an error instead of an answer', () => {
  const collapsed =
    'Based on Cambodia Customs regulations: ### Conditions for Import or Export * Import or export of any item in the list is subject to: * Absolute prohibition on import or export; or, * License, permit, or certificates as well as other legal documents in similar form, prior to its import or export, or under other specific treatment required by competent authorities.';
  const response = baseGeneralResponse({
    response: {
      type: 'markdown',
      content: collapsed,
      coverage: 'partial',
      confidence: 'medium',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [{ type: 'markdown', text: collapsed }],
    },
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.status, 'failed');
  assert.equal(parts!.blocks[0].type, 'error');
  assert.equal(parts!.blocks[0].content.title, 'Response unavailable');
  assert.equal(
    parts!.blocks[0].content.message,
    'The service could not generate a reliable answer for this request. Please try again.',
  );
  assert.equal(parts!.content.includes('Conditions for Import or Export'), false);
});

test('normalized response renders suggestions only from message content when top-level suggestions also exist', () => {
  const suggestions = [
    'How do I classify my goods?',
    'How is customs duty calculated?',
  ];
  const response = baseGeneralResponse({
    suggestions,
    message: {
      role: 'assistant',
      content: [
        {
          type: 'markdown',
          text: 'Customs valuation is the process of determining the value of imported goods.',
        },
        {
          type: 'suggestions',
          title: 'Suggested follow-ups',
          items: suggestions,
        },
      ],
    },
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);

  const suggestionBlocks = parts!.blocks.filter((block) => block.type === 'suggestions');
  assert.equal(suggestionBlocks.length, 1);
  assert.deepEqual(suggestionBlocks[0].content, suggestions);

  for (const suggestion of suggestions) {
    const renderedCount = suggestionBlocks.flatMap((block) => block.content as string[])
      .filter((item) => item === suggestion).length;
    assert.equal(renderedCount, 1);
  }
});

test('successful general response converts citations to frontend sources', () => {
  const response = baseGeneralResponse({
    citations: [
      {
        id: '1021',
        marker: 1,
        label: 'Source 1',
        title: 'Conditions for Import or Export',
        snippet: 'Conditions for Import or Export...',
        score: 0.9358,
        document_id: '1021',
        metadata: {},
      },
    ],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.sources.length, 1);
  assert.equal(parts!.sources.length, response.citations.length);
  assert.equal(parts!.blocks.some((block) => String(block.type) === 'references'), false);
  assert.equal(parts!.sources[0].marker, 1);
  assert.equal(parts!.sources[0].title, 'Conditions for Import or Export');
  assert.equal(parts!.sources[0].snippet, 'Conditions for Import or Export...');
  assert.equal(parts!.sources[0].documentId, '1021');
});

test('general response with citations only keeps markdown block and exposes sources separately', () => {
  const response = baseGeneralResponse({
    message: {
      role: 'assistant',
      content: [{ type: 'markdown', text: 'Citation-only answer.' }],
    },
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'Citation-only answer.',
      limitations: [],
    },
    citations: [
      {
        id: '1021',
        marker: 1,
        label: 'Source 1',
        title: 'Conditions for Import or Export',
        document_id: '1021',
        metadata: {},
      },
    ],
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown']);
  assert.equal(parts!.sources.length, 1);
  assert.equal(parts!.sources.length, response.citations.length);
  assert.equal(parts!.blocks.some((block) => String(block.type) === 'references'), false);
  assert.equal(parts!.sources[0].documentId, '1021');
});

test('general response with clarification maps markdown then clarification', () => {
  const response = baseGeneralResponse({
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'I need a little more information.' },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: [
            'What product are you importing?',
            'Which country is the product coming from?',
          ],
        },
      ],
    },
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'I need a little more information.',
      limitations: [],
    },
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'clarification']);
  assert.deepEqual(parts!.blocks[1].content.fields.map((field) => field.label), [
    'What product are you importing?',
    'Which country is the product coming from?',
  ]);
});

test('retrieval clarification_required status preserves workflow state and renders answer plus clarification', () => {
  const response = baseGeneralResponse({
    service: 'retrieval',
    intent: 'hs_code_lookup',
    status: 'clarification_required',
    query: 'What is the HS code for cotton fabric?',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'The service needs more detail about the cotton fabric.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        {
          type: 'markdown',
          text: 'The service needs more detail about the cotton fabric.',
        },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: ['Is the cotton fabric woven, knitted, or crocheted?'],
        },
      ],
    },
    clarifications: ['Is the cotton fabric woven, knitted, or crocheted?'],
    suggestions: [],
  });

  assert.equal(isNormalizedChatResponse(response), true);

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.status, 'clarification_required');
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'clarification']);
  assert.equal(parts!.blocks[0].content, 'The service needs more detail about the cotton fabric.');
  assert.deepEqual(parts!.blocks[1].content.fields.map((field) => field.label), [
    'Is the cotton fabric woven, knitted, or crocheted?',
  ]);
});

test('retrieval clarification block renders all upstream clarification questions after markdown', () => {
  const questions = [
    'What is the exact fiber composition?',
    'Is the fabric dyed or unbleached?',
    'What is the weight in g/m²?',
  ];
  const response = baseGeneralResponse({
    service: 'retrieval',
    intent: 'hs_code_lookup',
    status: 'clarification_required',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'The service needs more detail before confirming the HS code.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        {
          type: 'markdown',
          text: 'The service needs more detail before confirming the HS code.',
        },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions,
        },
      ],
    },
    clarifications: questions,
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.status, 'clarification_required');
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'clarification']);
  assert.deepEqual(parts!.blocks[1].content.fields.map((field) => field.label), questions);
});

test('retrieval hs-code markdown preserves all service-generated candidates and wording', () => {
  const answer = `Candidate HS codes for cotton fabric:

1. 5208.11.00 - Woven fabrics of cotton, unbleached, plain weave.
Reasoning: Candidate returned first by the retrieval service. [Document 1]

2. 5209.11.00 - Woven fabrics of cotton, bleached, plain weave.
Reasoning: Candidate returned second by the retrieval service. [Document 2]

3. 5210.11.00 - Woven fabrics of cotton mixed with man-made fibres.
Reasoning: Candidate returned third by the retrieval service. [Document 3]`;
  const response = baseGeneralResponse({
    service: 'retrieval',
    intent: 'hs_code_lookup',
    status: 'clarification_required',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: answer,
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: answer },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: ['What is the fabric weight and cotton composition?'],
        },
      ],
    },
    clarifications: ['What is the fabric weight and cotton composition?'],
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.content, answer);
  assert.equal(parts!.blocks[0].content, answer);
  assert.equal(parts!.blocks[0].content.includes('5208.11.00'), true);
  assert.equal(parts!.blocks[0].content.includes('5209.11.00'), true);
  assert.equal(parts!.blocks[0].content.includes('5210.11.00'), true);
  assert.ok(parts!.blocks[0].content.indexOf('5208.11.00') < parts!.blocks[0].content.indexOf('5209.11.00'));
  assert.ok(parts!.blocks[0].content.indexOf('5209.11.00') < parts!.blocks[0].content.indexOf('5210.11.00'));
  assert.equal(parts!.blocks[0].content.includes('[Document 1]'), true);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'clarification']);
});

test('retrieval classification confidence stays separate from citation relevance scores', () => {
  const response = baseGeneralResponse({
    service: 'retrieval',
    intent: 'hs_code_lookup',
    confidence: 'low',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      confidence: 'low',
      content: 'Candidate 1: 5208.11.00. Candidate 2: 5209.11.00.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Candidate 1: 5208.11.00. Candidate 2: 5209.11.00.' },
      ],
    },
    citations: [
      {
        id: 'doc-1',
        marker: 1,
        label: 'Source 1',
        title: 'Cotton Fabric Reference',
        score: 0.95,
        document_id: 'doc-1',
        metadata: {},
      },
    ],
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.confidence, 'low');
  assert.equal(parts!.sources[0].title, 'Cotton Fabric Reference');
  assert.equal('score' in parts!.sources[0], false);
});

test('retrieval structured hs-code prediction block maps to prediction renderer content', () => {
  const response = baseGeneralResponse({
    service: 'retrieval',
    intent: 'hs_code_lookup',
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'The HS classification is preliminary and needs confirmation.',
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [
        {
          type: 'markdown',
          text: 'The HS classification is preliminary and needs confirmation.',
        },
        {
          type: 'prediction',
          title: 'Preliminary HS Code',
          data: {
            hsCode: '5208.39.00',
            description: 'Other dyed woven cotton fabrics',
            confidence: 'low',
            preliminary: true,
            alternatives: [
              {
                hsCode: '5208.32.00',
                productName: 'Other dyed woven cotton fabrics',
                confidence: 0.22,
              },
            ],
          },
        },
        {
          type: 'table',
          title: 'Possible HS Code Matches',
          columns: [
            { key: 'rank', label: 'Rank' },
            { key: 'hs_code', label: 'HS Code' },
            { key: 'description', label: 'Description' },
            { key: 'retrieval_score', label: 'Match Score' },
          ],
          rows: [
            {
              rank: 1,
              hs_code: '5208.39.00',
              description: 'Other dyed woven cotton fabrics',
              retrieval_score: 0.95,
            },
          ],
        },
      ],
    },
    suggestions: [],
  });

  assert.equal(isNormalizedChatResponse(response), true);

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'prediction', 'table']);
  assert.equal(parts!.blocks[1].title, 'Preliminary HS Code');
  assert.equal(parts!.blocks[1].content.hsCode, '5208.39.00');
  assert.equal(parts!.blocks[1].content.productName, 'Other dyed woven cotton fabrics');
  assert.equal(parts!.blocks[1].content.preliminary, true);
  assert.equal('confidenceLabel' in parts!.blocks[1].content, false);
  assert.equal('confidence' in parts!.blocks[1].content, false);
  assert.equal('confidence' in parts!.blocks[1].content.alternatives[0], false);
  assert.deepEqual(parts!.blocks[2].content.columns.map((column) => column.key), [
    'rank',
    'hs_code',
    'description',
  ]);
  assert.equal('retrieval_score' in parts!.blocks[2].content.rows[0], false);
});

test('general clarification fixture renders through clarification block mapping', () => {
  const response = baseGeneralResponse({
    message: {
      role: 'assistant',
      content: [
        {
          type: 'markdown',
          text: 'I need more information.',
        },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: [
            'What product are you importing?',
            'Which country is it coming from?',
          ],
        },
      ],
    },
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'I need more information.',
      limitations: [],
    },
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'clarification']);
  assert.equal(parts!.blocks[0].content, 'I need more information.');
  assert.equal(parts!.blocks[1].title, 'More information is needed');
  assert.deepEqual(parts!.blocks[1].content.fields.map((field) => field.label), [
    'What product are you importing?',
    'Which country is it coming from?',
  ]);
  assert.deepEqual(parts!.blocks[1].content.actions, [
    { id: 'submit', label: 'Submit', primary: true },
  ]);
});

test('general response with partial coverage maps markdown then coverage', () => {
  const response = baseGeneralResponse({
    coverage: 'partial',
    response: {
      type: 'markdown',
      coverage: 'partial',
      content: 'Partial answer.',
      limitations: [{ message: 'The exact requirements depend on the product and HS code.' }],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Partial answer.' },
        {
          type: 'coverage',
          title: 'Information limitation',
          tone: 'warning',
          items: ['The exact requirements depend on the product and HS code.'],
        },
      ],
    },
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'coverage']);
  assert.equal(parts!.coverage, 'partial');
  assert.equal(parts!.blocks[1].content.tone, 'warning');
});

test('general supported blocks map through generic block types in recommended order', () => {
  const response = baseGeneralResponse({
    coverage: 'partial',
    response: {
      type: 'markdown',
      coverage: 'partial',
      content: 'General answer.',
      limitations: [{ message: 'Coverage is limited.' }],
    },
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'General answer.' },
        {
          type: 'coverage',
          title: 'Information limitation',
          tone: 'warning',
          items: ['Coverage is limited.'],
        },
        {
          type: 'official_reference',
          title: 'Official GDCE tariff lookup',
          label: 'Verify on the official GDCE tariff lookup',
          url: 'https://customs.gov.kh/en/publications/14037-customs-tariff-of-cambodia-km-2022',
          agency: 'GDCE',
          source_type: 'official_tariff',
        },
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: ['Which procedure are you asking about?'],
        },
        {
          type: 'suggestions',
          title: 'Suggested follow-ups',
          items: ['What documents are needed?'],
        },
      ],
    },
    suggestions: ['What documents are needed?'],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), [
    'markdown',
    'coverage',
    'official_reference',
    'clarification',
    'suggestions',
  ]);
  assert.equal(parts!.blocks[0].content, 'General answer.');
  assert.equal(parts!.blocks[1].content.items[0], 'Coverage is limited.');
  assert.equal(parts!.blocks[2].content.url, 'https://customs.gov.kh/en/publications/14037-customs-tariff-of-cambodia-km-2022');
  assert.equal(parts!.blocks[2].content.sourceType, 'official_tariff');
  assert.equal(parts!.blocks[3].content.fields[0].label, 'Which procedure are you asking about?');
  assert.deepEqual(parts!.blocks[4].content, ['What documents are needed?']);
});

test('general references block is supported as a generic normalized block', () => {
  const response = baseGeneralResponse({
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'General answer with inline references.' },
        {
          type: 'references',
          title: 'References',
          items: [{ id: 'ref-1', title: 'GDCE Public Guidance' }],
        },
      ],
    },
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: 'General answer with inline references.',
      limitations: [],
    },
    citations: [],
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'references']);
  assert.equal(parts!.blocks[1].type, 'references');
  assert.equal(parts!.blocks[1].content.items[0].title, 'GDCE Public Guidance');
});

test('failed general response maps to error block', () => {
  const response = baseGeneralResponse({
    status: 'failed',
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
    suggestions: [],
  });

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.status, 'failed');
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['error']);
  assert.equal(parts!.blocks[0].content.message, 'The general service is temporarily unavailable.');
});

test('malformed general response does not crash and returns safe error', () => {
  const response = {
    ...(readFixture('normalized-general-response.json') as Record<string, unknown>),
    message: { role: 'assistant' },
  };

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.status, 'failed');
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['error']);
});

test('handleNormalizedChatResponse validates and converts normalized responses directly', () => {
  const response = readFixture('normalized-general-response.json');

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.deepEqual(parts!.blocks.map((block) => block.type), ['markdown', 'suggestions']);
  assert.equal(parts!.status, 'completed');
  assert.equal(parts!.latencyMs, 125);
});

test('handleNormalizedChatResponse returns safe error for invalid normalized envelopes', () => {
  const response = {
    ...(readFixture('normalized-general-response.json') as Record<string, unknown>),
    status: 'done',
  };

  const parts = handleNormalizedChatResponse(response, 'fallback-id');

  assert.notEqual(parts, null);
  assert.equal(parts!.status, 'failed');
  assert.equal(parts!.blocks[0].type, 'error');
  assert.equal(parts!.blocks[0].content.message, 'The response format was not supported.');
});

test('handleNormalizedChatResponse leaves legacy payloads for legacy parsers', () => {
  const parts = handleNormalizedChatResponse({ answer: 'Legacy answer.' }, 'fallback-id');

  assert.equal(parts, null);
});

test('zod schema validates required normalized response fields', () => {
  const response = readFixture('normalized-general-response.json') as Record<string, unknown>;

  assert.notEqual(parseNormalizedChatResponse(response), null);
  assert.equal(parseNormalizedChatResponse({ ...response, request_id: 123 }), null);
  assert.equal(parseNormalizedChatResponse({ ...response, session_id: null }), null);
  assert.equal(parseNormalizedChatResponse({ ...response, status: 'done' }), null);
  assert.equal(parseNormalizedChatResponse({ ...response, message: { role: 'assistant' } }), null);
  assert.equal(parseNormalizedChatResponse({ ...response, citations: 'not-an-array' }), null);
});

test('zod schema accepts normalized v1 calculator arrays without a version bump', () => {
  const response = {
    ...(readFixture('normalized-general-response.json') as Record<string, unknown>),
    service: 'calculator',
    intent: 'calculation',
    clarifications: ['Which origin country should I use?'],
    errors: [
      'Calculator upstream warning',
      {
        code: 'CALCULATOR_SERVICE_UNAVAILABLE',
        message: 'The calculator service is temporarily unavailable.',
        retryable: true,
      },
    ],
  };

  const parsed = parseNormalizedChatResponse(response);

  assert.notEqual(parsed, null);
  assert.equal(parsed!.api_version, '1.0');
  assert.deepEqual(parsed!.clarifications, ['Which origin country should I use?']);
  assert.deepEqual(parsed!.errors, [
    'Calculator upstream warning',
    {
      code: 'CALCULATOR_SERVICE_UNAVAILABLE',
      message: 'The calculator service is temporarily unavailable.',
      retryable: true,
    },
  ]);
});

test('unknown future blocks become safe fallback blocks without raw json', () => {
  const response = {
    ...(readFixture('normalized-general-response.json') as Record<string, unknown>),
    message: {
      role: 'assistant',
      content: [
        { type: 'markdown', text: 'Known content.' },
        { type: 'future_block', sensitive: 'do not render this raw' },
      ],
    },
  };

  assert.equal(isNormalizedChatResponse(response), true);

  const parts = normalizedChatResponseToMessageParts(response as NormalizedChatResponse, 'fallback-id');

  assert.deepEqual(parts.blocks.map((block) => block.type), ['markdown', 'fallback']);
  assert.equal(parts.blocks[1].content, 'Unsupported response content');
  assert.equal(String(parts.blocks[1].content).includes('sensitive'), false);
});

test('document markers in answer text are preserved and citations stay separate', () => {
  const answer = 'Required documents must be complete (Document 1). Restrictions may also apply (Document 4).';
  const response = {
    ...(readFixture('normalized-general-response.json') as NormalizedChatResponse),
    response: {
      type: 'markdown',
      coverage: 'unknown',
      content: answer,
      limitations: [],
    },
    message: {
      role: 'assistant',
      content: [{ type: 'markdown', text: answer }],
    },
    citations: [
      {
        id: '1021',
        marker: 1,
        label: 'Source 1',
        title: 'Conditions for Import or Export',
        document_id: '1021',
        metadata: {},
      },
    ],
  } satisfies NormalizedChatResponse;

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.blocks[0].type, 'markdown');
  assert.equal(parts.blocks[0].content, answer);
  assert.equal(parts.blocks[0].content.includes('(Document 1)'), true);
  assert.equal(parts.blocks[0].content.includes('(Document 4)'), true);
  assert.equal(parts.sources[0].marker, 1);
  assert.equal(parts.sources[0].title, 'Conditions for Import or Export');
});

test('clarification blocks stay first-class block types and render as forms', () => {
  const response = {
    ...(readFixture('normalized-general-response.json') as NormalizedChatResponse),
    message: {
      role: 'assistant',
      content: [
        {
          type: 'clarification',
          title: 'More information is needed',
          questions: [
            'What product are you importing?',
            'Which country is the product coming from?',
          ],
        },
      ],
    },
  } satisfies NormalizedChatResponse;

  const parts = normalizedChatResponseToMessageParts(response, 'fallback-id');

  assert.equal(parts.blocks[0].type, 'clarification');
  assert.equal(parts.blocks[0].title, 'More information is needed');
  assert.deepEqual(parts.blocks[0].content.fields.map((field) => field.label), [
    'What product are you importing?',
    'Which country is the product coming from?',
  ]);
});

test('ChatMessageRenderer stays block-type driven with no service-specific branch', () => {
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'components', 'chat', 'ChatMessageRenderer.vue'),
    'utf8',
  );

  assert.match(source, /resolveRenderer\(block\.type\)/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]general['"]/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]general['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]calculation['"]/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]calculator['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]trade_query['"]/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]trade['"]/);
  assert.doesNotMatch(source, /hs_?code/i);
  assert.doesNotMatch(source, /productCategory|product category/i);
  assert.doesNotMatch(source, /GeneralQuestionRenderer/);
  assert.doesNotMatch(source, /Trade(Renderer|StatisticsRenderer|QueryRenderer)/);
});

test('chat render flow uses message blocks as the visual source before content fallback parsing', () => {
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'composables', 'chat', 'useChatMessageRenderFlow.ts'),
    'utf8',
  );

  assert.match(source, /if \(props\.message\.blocks\?\.length\) return props\.message\.blocks;/);
  assert.match(source, /return parseBlocks\(props\.message\.content\);/);
  assert.ok(
    source.indexOf('if (props.message.blocks?.length) return props.message.blocks;') <
      source.indexOf('return parseBlocks(props.message.content);'),
  );
});

test('renderer registry supports normalized data blocks without a service-specific renderer', () => {
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'composables', 'renderers', 'useRenderer.ts'),
    'utf8',
  );

  for (const type of [
    'markdown',
    'table',
    'chart',
    'prediction',
    'clarification',
    'suggestions',
	    'coverage',
	    'references',
	    'official_reference',
	    'error',
  ]) {
    assert.match(source, new RegExp(`${type}:`));
  }

  assert.match(source, /canonicalizeBlockType\(type\)/);
  assert.match(source, /rendererMap\[canonical\]\s*\?\?\s*MarkdownRenderer/);
  assert.doesNotMatch(source, /fallback:\s*MarkdownRenderer/);
  assert.doesNotMatch(source, /GeneralRenderer/);
  assert.doesNotMatch(source, /RetrievalRenderer/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]general['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]general['"]/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]retrieval['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]hs_code_lookup['"]/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]trade['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]trade_query['"]/);
  assert.doesNotMatch(source, /Trade(Renderer|StatisticsRenderer|QueryRenderer)/);
});

test('trade blocks resolve through existing generic renderer components by block type', () => {
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'composables', 'renderers', 'useRenderer.ts'),
    'utf8',
  );

  for (const [type, renderer] of [
    ['markdown', 'MarkdownRenderer'],
    ['summary', 'SummaryRenderer'],
    ['table', 'TableRenderer'],
    ['chart', 'ChartTaskRenderer'],
    ['coverage', 'CoverageRenderer'],
    ['clarification', 'InteractionRenderer'],
    ['suggestions', 'SuggestionsRenderer'],
    ['error', 'ErrorRenderer'],
  ]) {
    assert.match(source, new RegExp(`${type}: ${renderer}`));
  }

  assert.match(source, /resolveRenderer\(type: string\)/);
  assert.match(source, /canonicalizeBlockType\(type\)/);
  assert.match(source, /rendererMap\[canonical\]\s*\?\?\s*MarkdownRenderer/);
  assert.doesNotMatch(source, /interaction:\s*InteractionRenderer/);
  assert.doesNotMatch(source, /fallback:\s*MarkdownRenderer/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]trade['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]trade_query['"]/);
  assert.doesNotMatch(source, /Trade(Renderer|StatisticsRenderer|QueryRenderer)/);
});

test('trade suggestions use the generic clickable suggestions renderer', () => {
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'components', 'renderers', 'SuggestionsRenderer.vue'),
    'utf8',
  );

  assert.match(source, /<button/);
  assert.match(source, /@click="sendSuggestion\(suggestion\)"/);
  assert.match(source, /action: 'send_suggestion'/);
  assert.doesNotMatch(source, /service\s*={2,3}\s*['"]trade['"]/);
  assert.doesNotMatch(source, /intent\s*={2,3}\s*['"]trade_query['"]/);
});

test('trade renderers may format display text but do not locally convert units currencies or percentages', () => {
  const rendererDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'components', 'renderers');
  const composableDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'app', 'composables', 'renderers');
  const sources = [
    'TableRenderer.vue',
    'SummaryRenderer.vue',
    'ChartTaskRenderer.vue',
  ].map((name) => readFileSync(join(rendererDir, name), 'utf8')).join('\n');
  const composables = [
    'useTableRenderer.ts',
    'useChartRenderer.ts',
  ].map((name) => readFileSync(join(composableDir, name), 'utf8')).join('\n');
  const combined = `${sources}\n${composables}`;

  assert.match(sources, /toLocaleString|tableToClipboardText|v-html/);
  assert.doesNotMatch(combined, /USD\s*['"]?\s*:\s*['"]?KHR|KHR\s*['"]?\s*:\s*['"]?USD/);
  assert.doesNotMatch(combined, /value_usd\s*\*\s*[0-9]|value_usd\s*\/\s*[0-9]/);
  assert.doesNotMatch(combined, /weight_kg\s*\/\s*1000|tonnes|metric tons/i);
  assert.doesNotMatch(combined, /share_percent\s*=\s*|growth_rate_pct\s*=/);
  assert.doesNotMatch(combined, /sort\(/);
});
