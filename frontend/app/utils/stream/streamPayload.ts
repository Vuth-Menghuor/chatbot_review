/**
 * Parse one SSE "frame" (lines with `event:` / `data:`) from LM Studio’s OpenAI-style stream.
 */
export function parseSseFrame(frame: string): { event?: string; data: string } {
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

  return { event, data };
}
