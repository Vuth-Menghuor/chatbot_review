import test from 'node:test';
import assert from 'node:assert/strict';

import { parseSseFrame, readSseStream } from '../../app/utils/stream';

function streamFromChunks(chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

test('parseSseFrame parses event names and JSON data safely', () => {
  assert.deepEqual(parseSseFrame('event: delta\ndata: {"content":"hello"}'), {
    event: 'delta',
    data: '{"content":"hello"}',
    json: { content: 'hello' },
  });

  assert.deepEqual(parseSseFrame('event: delta\ndata: {bad json'), {
    event: 'delta',
    data: '{bad json',
  });

  assert.equal(parseSseFrame('event: ping'), null);
});

test('readSseStream preserves incomplete frames across chunks', async () => {
  const events: Array<{ event: string; json?: unknown }> = [];

  await readSseStream(
    streamFromChunks([
      'event: sta',
      'rt\ndata: {"request_id":"request-1"}\n\n',
      'event: delta\ndata: {"content":"The "}\n',
      '\nevent: done\ndata: {"status":"completed"}\n\n',
    ]),
    (event) => {
      events.push({ event: event.event, json: event.json });
    },
  );

  assert.deepEqual(events, [
    { event: 'start', json: { request_id: 'request-1' } },
    { event: 'delta', json: { content: 'The ' } },
    { event: 'done', json: { status: 'completed' } },
  ]);
});

test('readSseStream keeps partial event names and trailing incomplete frames buffered', async () => {
  const events: Array<{ event: string; json?: unknown }> = [];

  await readSseStream(
    streamFromChunks([
      'event: del',
      'ta\ndata: {"content":"Hello"}\n\n',
      'event:',
    ]),
    (event) => {
      events.push({ event: event.event, json: event.json });
    },
  );

  assert.deepEqual(events, [
    { event: 'delta', json: { content: 'Hello' } },
  ]);
});

test('readSseStream ignores comments and malformed data without throwing', async () => {
  const events: Array<{ event: string; data: string; json?: unknown }> = [];

  await readSseStream(
    streamFromChunks([
      ': keepalive\n\n',
      'event: delta\ndata: {bad json\n\n',
      'event: delta\ndata: {"content":"ok"}\n\n',
    ]),
    (event) => {
      events.push({ event: event.event, data: event.data, json: event.json });
    },
  );

  assert.deepEqual(events, [
    { event: 'delta', data: '{bad json', json: undefined },
    { event: 'delta', data: '{"content":"ok"}', json: { content: 'ok' } },
  ]);
});

test('readSseStream stops cleanly when aborted before reading', async () => {
  const controller = new AbortController();
  controller.abort();
  const events: unknown[] = [];

  await readSseStream(
    streamFromChunks(['event: delta\ndata: {"content":"hidden"}\n\n']),
    (event) => {
      events.push(event);
    },
    { signal: controller.signal },
  );

  assert.deepEqual(events, []);
});
