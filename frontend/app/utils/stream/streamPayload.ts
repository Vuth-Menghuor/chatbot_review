export interface ParsedSseFrame {
  event?: string;
  data: string;
  json?: unknown;
}

export interface SseDispatchEvent {
  event: string;
  data: string;
  json?: unknown;
}

/**
 * Parse one SSE frame (lines with `event:` / `data:`). The caller decides
 * whether malformed JSON is fatal.
 */
export function parseSseFrame(frame: string): ParsedSseFrame | null {
  const lines = frame.split('\n');
  const event = lines
    .find((line) => line.startsWith('event:'))
    ?.replace(/^event:\s?/, '')
    ?.trim();

  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace(/^data:\s?/, ''))
    .join('\n')
    .trim();

  if (!data) return null;

  try {
    return { event, data, json: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}

export async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SseDispatchEvent) => void | Promise<void>,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      if (options.signal?.aborted) {
        await reader.cancel();
        return;
      }

      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        await dispatchSseFrame(frame, onEvent);
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      await dispatchSseFrame(buffer, onEvent);
    }
  } finally {
    reader.releaseLock();
  }
}

async function dispatchSseFrame(
  frame: string,
  onEvent: (event: SseDispatchEvent) => void | Promise<void>,
) {
  if (!frame.trim() || frame.trimStart().startsWith(':')) return;
  const parsed = parseSseFrame(frame);
  if (!parsed) return;
  await onEvent({
    event: parsed.event || 'message',
    data: parsed.data,
    json: parsed.json,
  });
}
