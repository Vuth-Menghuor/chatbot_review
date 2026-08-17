import test from 'node:test';
import assert from 'node:assert/strict';
import { ref } from 'vue';

import { useUiBlockInjection } from '../../app/composables/chat/useUiBlockInjection';
import type { Message, MessageBlock } from '../../app/types/message';

test('useUiBlockInjection drops unreliable fallback markdown and empty tables when useful blocks exist', () => {
  const messages = ref<Message[]>([
    {
      id: 'assistant-1',
      role: 'assistant',
      status: 'streaming',
      responseStatus: 'processing',
      content: '',
    },
  ]);
  const blocks: MessageBlock[] = [
    {
      id: 'bad-markdown',
      type: 'markdown',
      content: 'SUMMARY OF KEY FINDINGS:\nThe provided trade data contains specific figures and insights.',
      isComplete: true,
    },
    {
      id: 'empty-table',
      type: 'table',
      title: 'Trade Volume Ranking',
      content: {
        columns: [{ key: 'country', title: 'Country' }],
        rows: [],
      },
      isComplete: true,
    },
    {
      id: 'chart',
      type: 'chart',
      title: 'Trade Volume Ranking',
      content: {
        chartType: 'pie',
        data: [
          { label: 'China', value: 9830000000 },
          { label: 'Thailand', value: 1170000000 },
          { label: 'Indonesia', value: 869590000 },
          { label: 'Singapore', value: 763150000 },
          { label: 'Malaysia', value: 640850000 },
        ],
      },
      isComplete: true,
    },
    {
      id: 'coverage',
      type: 'coverage',
      title: 'Data availability',
      content: {
        tone: 'warning',
        items: ['Some sea transport records may be incomplete.'],
      },
      isComplete: true,
    },
  ];

  useUiBlockInjection({ messages }).upsertAssistantMessage(
    'assistant-1',
    'SUMMARY OF KEY FINDINGS:\nThe provided trade data contains specific figures and insights.',
    {
    status: 'completed',
    responseStatus: 'completed',
    blocks,
    responseMode: 'stream',
    progressStage: 'completed',
    },
  );

  const assistant = messages.value[0]!;

  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
  assert.equal(assistant.error, undefined);
  assert.equal(assistant.content.includes('Response unavailable'), false);
  assert.equal(assistant.content.includes('SUMMARY OF KEY FINDINGS'), false);
  assert.deepEqual(assistant.blocks?.map((block) => block.type), ['chart', 'coverage']);
  assert.equal((assistant.blocks?.[0]?.content as Record<string, unknown>).chartType, 'pie');
  assert.equal(((assistant.blocks?.[0]?.content as Record<string, unknown>).data as unknown[]).length, 5);
});

test('useUiBlockInjection refuses to erase visible assistant content with empty completed update', () => {
  const messages = ref<Message[]>([
    {
      id: 'assistant-1',
      role: 'assistant',
      status: 'streaming',
      responseStatus: 'processing',
      content: 'Hello! How can I help you today?',
      streamingContent: 'Hello! How can I help you today?',
      blocks: [
        {
          id: 'assistant-1-streaming-markdown',
          type: 'markdown',
          content: 'Hello! How can I help you today?',
          isComplete: false,
        },
      ],
    },
  ]);

  useUiBlockInjection({ messages }).upsertAssistantMessage('assistant-1', '', {
    status: 'completed',
    responseStatus: 'completed',
    blocks: [],
    responseMode: 'stream',
    progressStage: 'completed',
    streamingContent: '',
  });

  const assistant = messages.value[0]!;

  assert.equal(assistant.status, 'completed');
  assert.equal(assistant.responseStatus, 'completed');
  assert.equal(assistant.content, 'Hello! How can I help you today?');
  assert.equal(assistant.blocks?.[0]?.content, 'Hello! How can I help you today?');
  assert.equal(assistant.streamingContent, '');
});
