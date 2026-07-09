import type { Message, UnifiedToolResponse } from '~/types/message';
import { scheduleDeferredLocalChartTaskMerges } from '~/composables/chat/useAsyncToolTaskPoll';
import { parseAiResponseWithAsyncTasks } from '~/utils/message';

/** Same shape as `DeferredLocalChartTaskMergeArgs` without `asyncTasks` (filled from parse). */
export interface ScheduleLocalChartMergesChatDeps {
  assistantMsgId: string;
  signal: AbortSignal;
  getAssistantMessage: (messageId: string) => Message | null;
  upsertAssistantMessage: (
    messageId: string,
    content: string,
    meta?: { generationDurationMs?: number },
  ) => void;
}

/**
 * Non-streaming helper: parses `input` the same way as `parseAiResponse` for unified JSON
 * envelopes (string or object), then schedules rAF merges for **frontend-only** `local-chart:`
 * tasks.
 *
 * **Input shape:** use a `UnifiedToolResponse` object, or a raw JSON string that
 * `tryParseEnvelopeString` recognizes (`{ "requestId", "tools", ... }`). If you only have
 * legacy marker text from `unifiedResponseToMarkerText`, this cannot recover `asyncTasks` —
 * pass the original `UnifiedToolResponse` instead, or call `scheduleDeferredLocalChartTaskMerges`
 * with `normalizeUnifiedToolResponse(envelope).asyncTasks` alongside your persisted content.
 *
 * - Does **not** perform HTTP polling (use `pollAsyncToolTasksWhenEnabled` for real server tasks).
 * - Does **not** send `local-chart:*` ids to the server — they never leave the client.
 *
 * Call after the assistant message content is persisted so the merge step can read the message
 * and replace the processing chart row in-place.
 */
export function scheduleLocalChartDeferredMergesAfterAiParse(
  deps: ScheduleLocalChartMergesChatDeps,
  input: string | UnifiedToolResponse,
): void {
  const { asyncTasks } = parseAiResponseWithAsyncTasks(input);
  if (!asyncTasks.length) return;
  void scheduleDeferredLocalChartTaskMerges({ ...deps, asyncTasks });
}
