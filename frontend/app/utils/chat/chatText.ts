import striptags from 'striptags';
import { normalizeLatexInMarkdown } from '~/utils/markdown';
import { tApp } from '~/utils/i18n/tApp';

export function generateChatTitle(text: string): string {
  const plainText = striptags(text || '')
    .replace(/[`*_~>#-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  const clean = plainText
    .replace(
      /^(hey|hi|hello|can you|could you|please|i want|i need|what is|what are|how to|how do i|explain|tell me about)\s+/i,
      '',
    )
    .replace(/[?!.]+$/, '')
    .trim();

  if (!clean) return tApp('chat.newChat', 'New Chat');

  const titled = clean.charAt(0).toUpperCase() + clean.slice(1);
  if (titled.length <= 60) return titled;

  const truncated = titled.slice(0, 60);
  return (
    (truncated.lastIndexOf(' ') > 30 ? truncated.slice(0, truncated.lastIndexOf(' ')) : truncated) +
    '...'
  );
}

/**
 * Coerce and clean assistant message text before it hits the UI / markdown pipeline.
 * Avoids NUL/BOM glitches and inconsistent newlines from APIs or LM Studio.
 */
export function normalizeAssistantContentForUi(raw: unknown): string {
  if (raw == null) return '';
  const s = typeof raw === 'string' ? raw : String(raw);
  return normalizeLatexInMarkdown(
    s
      .replace(/^\uFEFF/, '')
      .replace(/\0/g, '')
      .replace(/\u200B/g, '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n'),
  );
}
