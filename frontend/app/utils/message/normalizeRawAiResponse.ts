import type { MessageBlock, UnifiedAsyncTaskState, UnifiedToolResponse } from '~/types/message';
import { tryParseJsonLike } from '../json';
import {
  isUnifiedToolResponse,
  normalizeUnifiedToolResponse,
  unifiedResponseToMarkerText,
} from '../tool/unifiedToolResponse';
import { normalizeRawTextBlocks } from './normalizeRawTextBlocks';

export function normalizeRawAiResponse(rawText: string): MessageBlock[] {
  if (!rawText) return [];

  const envelope = tryParseEnvelopeString(rawText);
  if (envelope) {
    return normalizeUnifiedToolResponse(envelope).blocks;
  }

  return normalizeRawTextBlocks(rawText);
}

export function parseAiResponse(
  input: string | UnifiedToolResponse | null | undefined,
): MessageBlock[] {
  if (!input) return [];
  if (typeof input === 'string') return normalizeRawAiResponse(input);
  if (isUnifiedToolResponse(input)) return normalizeUnifiedToolResponse(input).blocks;
  return [];
}

export function parseAiResponseWithAsyncTasks(
  input: string | UnifiedToolResponse | null | undefined,
): { blocks: MessageBlock[]; asyncTasks: UnifiedAsyncTaskState[] } {
  if (!input) return { blocks: [], asyncTasks: [] };
  if (typeof input === 'string') {
    const envelope = tryParseEnvelopeString(input);
    if (envelope) {
      const r = normalizeUnifiedToolResponse(envelope);
      return { blocks: r.blocks, asyncTasks: r.asyncTasks };
    }
    return { blocks: normalizeRawAiResponse(input), asyncTasks: [] };
  }
  if (isUnifiedToolResponse(input)) {
    const r = normalizeUnifiedToolResponse(input);
    return { blocks: r.blocks, asyncTasks: r.asyncTasks };
  }
  return { blocks: [], asyncTasks: [] };
}

export function envelopeToMarkerText(envelope: UnifiedToolResponse): string {
  return unifiedResponseToMarkerText(envelope);
}

function tryParseEnvelopeString(text: string): UnifiedToolResponse | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{')) return null;
  if (!trimmed.includes('"requestId"') || !trimmed.includes('"tools"')) return null;

  const parsed = tryParseJsonLike(trimmed);
  return isUnifiedToolResponse(parsed) ? (parsed as UnifiedToolResponse) : null;
}
