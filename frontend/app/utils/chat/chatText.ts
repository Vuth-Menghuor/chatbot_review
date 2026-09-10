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

export const UNRELIABLE_SERVICE_FALLBACK_MESSAGE =
  'The service could not generate a reliable answer for this request. Please try again.';

type ServiceFallbackContext = {
  service?: unknown;
  intent?: unknown;
};

function normalizedContextValue(value: unknown) {
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

export function isUnreliableServiceFallbackText(text: unknown, context: ServiceFallbackContext = {}): boolean {
  if (typeof text !== 'string') return false;
  const service = normalizedContextValue(context.service);
  const intent = normalizedContextValue(context.intent);
  // An out-of-scope response is a deliberate, complete refusal. Some of its
  // guidance can legitimately mention contacting GDCE, which also appears in
  // the signatures used to reject unreliable trade-formatter drafts.
  if (intent === 'out_of_scope') return false;
  if (service === 'general' || intent === 'general') return false;
  if (service === 'calculator' || intent.includes('calc')) {
    return isCalculatorReportDraftText(text);
  }
  return isUnreliableTradeFormatterDraftText(text) || isCalculatorReportDraftText(text);
}

const TRADE_FORMATTER_HEADINGS = [
  'SUMMARY OF KEY FINDINGS',
  'DATA VISUALIZATION SUGGESTIONS',
  'YEAR-OVER-YEAR OR BILATERAL COMPARISONS',
  'TRENDS AND INSIGHTS',
];

export function isUnreliableTradeFormatterDraftText(text: unknown): boolean {
  if (typeof text !== 'string') return false;
  const normalized = text
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase();
  if (!normalized) return false;

  if (TRADE_FORMATTER_HEADINGS.some((heading) =>
    normalized.includes(heading) || (normalized.length >= 8 && heading.startsWith(normalized))
  )) {
    return true;
  }

  const lower = normalized.toLowerCase();
  return (
    lower.includes('the provided trade data contains') ||
    lower.includes('the provided trade data includes') ||
    lower.includes('contact gdce') ||
    lower.includes('contact the gdce') ||
    lower.includes('contact the general department of customs and excise') ||
    lower.includes('detailed figures require the full dataset') ||
    lower.includes('requires the full dataset') ||
    lower.includes('require the full dataset') ||
    lower.includes('full dataset for detailed figures')
  );
}

const CALCULATOR_REPORT_HEADINGS = [
  'IMPORT TAX CALCULATION',
  'EXPORT TAX CALCULATION',
  'SUMMARY OF CALCULATION',
  'PRODUCT INFORMATION',
  'INPUT PARAMETERS',
  'FINAL TAX BREAKDOWN',
  'ASSUMPTIONS & NOTES',
  'APPLICABLE RATES',
  'REFERENCES & CITATIONS',
  'DATA SOURCES',
];

export function isCalculatorReportDraftText(text: unknown): boolean {
  if (typeof text !== 'string') return false;
  const normalized = text
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase();
  if (!normalized) return false;

  if (CALCULATOR_REPORT_HEADINGS.some((heading) =>
    normalized.includes(heading) || (normalized.length >= 8 && heading.startsWith(normalized))
  )) {
    return true;
  }

  return /\bSTEP\s+\d+\s*:/i.test(text);
}
