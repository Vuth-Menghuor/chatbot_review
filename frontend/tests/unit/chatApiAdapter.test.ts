import test from 'node:test';
import assert from 'node:assert/strict';

import {
  chatApiResponseToUnified,
  canonicalizeChatApiTool,
  isChatApiResponse,
} from '../../app/services/chat-api/chatApiAdapter';
import type { ChatApiResponse } from '../../app/types/message';

test('chatApiAdapter recognizes chat API response envelopes', () => {
  assert.equal(isChatApiResponse({ output: [] }), true);
  assert.equal(isChatApiResponse({ output: [{ type: 'message', content: 'Hello' }] }), true);
  assert.equal(isChatApiResponse({ output: [{ type: 'unknown', content: 'Hello' }] }), false);
  assert.equal(isChatApiResponse({ message: { content: [] } }), false);
});

test('chatApiAdapter converts messages and table tool calls in order', () => {
  const response: ChatApiResponse = {
    response_id: 'chat-api-contract',
    output: [
      { type: 'message', content: 'Trade answer.' },
      {
        type: 'tool_call',
        tool: 'trade_table',
        status: 'completed',
        output: {
          columns: [{ key: 'partner_country', title: 'Partner Country' }],
          rows: [{ partner_country: 'Vietnam' }],
        },
      },
    ],
  };

  const unified = chatApiResponseToUnified(response, { timestamp: '2026-07-30T00:00:00.000Z' });

  assert.equal(unified.requestId, 'chat-api-contract');
  assert.equal(unified.mode, 'sync');
  assert.equal(unified.status, 'success');
  assert.deepEqual(unified.tools.map((tool) => tool.type), ['chat', 'table']);
  assert.equal(unified.tools[0].data, 'Trade answer.');
  assert.deepEqual(unified.tools[1].data, response.output[1].output);
});

test('chatApiAdapter preserves envelope errors and safely canonicalizes unknown tools', () => {
  const unified = chatApiResponseToUnified({
    response_id: 'error-contract',
    error: { message: 'Upstream failed', code: 'UPSTREAM_ERROR' },
    output: [
      {
        type: 'tool_call',
        tool: 'brand_new_tool',
        status: 'error',
        error: 'Tool failed',
        output: { raw: true },
      },
    ],
  });

  assert.equal(canonicalizeChatApiTool('brand_new_tool'), 'tool_output');
  assert.equal(unified.error?.message, 'Upstream failed');
  assert.equal(unified.tools[0].type, 'tool_output');
  assert.equal(unified.tools[0].status, 'error');
  assert.deepEqual(unified.tools[0].error, { message: 'Tool failed' });
});
