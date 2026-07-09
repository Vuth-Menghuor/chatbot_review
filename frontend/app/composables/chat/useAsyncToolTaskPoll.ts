import type { Message, MessageBlock, UnifiedAsyncTaskState } from '~/types/message';
import { blocksToMarkerText, normalizeRawAiResponse } from '~/utils/message';
import {
  isLocalChartTaskId,
  isLocalImageTaskId,
  isTaskPollTerminal,
  LOCAL_IMAGE_MOCK_DELAY_MS,
  mergePolledBlocksIntoBlocks,
  normalizeTaskPollBody,
  readTaskIdFromBlock,
  takeLocalChartTaskResolution,
  takeLocalImageTaskResolution,
} from '~/utils/tool';

function isLocalDeferredTaskId(taskId: string | undefined): boolean {
  return isLocalChartTaskId(taskId) || isLocalImageTaskId(taskId);
}

export interface PollAsyncToolTasksArgs {
  assistantMsgId: string;
  asyncTasks: UnifiedAsyncTaskState[];
  signal: AbortSignal;
  getAssistantMessage: (messageId: string) => Message | null;
  upsertAssistantMessage: (
    messageId: string,
    content: string,
    meta?: { generationDurationMs?: number; blocks?: MessageBlock[] },
  ) => void;
  /** Chat API base URL (used when `asyncTaskPollBaseUrl` is unset). */
  chatApiBaseUrl: string;
  apiToken?: string;
}

function interpolateTaskPath(template: string, taskId: string): string {
  return template.replace(/\{\{\s*taskId\s*\}\}/gi, encodeURIComponent(taskId));
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const t = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      signal.removeEventListener('abort', onAbort);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

function paintYield(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const id = requestAnimationFrame(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    });
    const onAbort = () => {
      cancelAnimationFrame(id);
      signal.removeEventListener('abort', onAbort);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export interface DeferredLocalChartTaskMergeArgs {
  assistantMsgId: string;
  asyncTasks: UnifiedAsyncTaskState[];
  signal: AbortSignal;
  getAssistantMessage: (messageId: string) => Message | null;
  upsertAssistantMessage: (
    messageId: string,
    content: string,
    meta?: { generationDurationMs?: number; blocks?: MessageBlock[] },
  ) => void;
}

function mergePolledBlocksIntoAssistantContent(
  assistantMsgId: string,
  polledBlocks: MessageBlock[],
  getAssistantMessage: DeferredLocalChartTaskMergeArgs['getAssistantMessage'],
  upsertAssistantMessage: DeferredLocalChartTaskMergeArgs['upsertAssistantMessage'],
): MessageBlock[] {
  const assistant = getAssistantMessage(assistantMsgId);
  const raw = assistant?.content ?? '';
  const existing = normalizeRawAiResponse(typeof raw === 'string' ? raw : String(raw));
  const merged = mergePolledBlocksIntoBlocks(existing, polledBlocks);
  upsertAssistantMessage(assistantMsgId, blocksToMarkerText(merged), { blocks: merged });
  return merged;
}

/**
 * Applies **frontend-only** coerced sync charts (`local-chart:` task ids) after one animation
 * frame so processing placeholders paint before ECharts mounts. Pass the full `asyncTasks` list
 * from `normalizeUnifiedToolResponse` / `parseAiResponseWithAsyncTasks` — non-local ids are ignored.
 */
export async function scheduleDeferredLocalChartTaskMerges(
  args: DeferredLocalChartTaskMergeArgs,
): Promise<void> {
  const locals = args.asyncTasks.filter((t) => isLocalDeferredTaskId(t.taskId));
  if (!locals.length) return;

  try {
    await paintYield(args.signal);
  } catch {
    return;
  }

  for (const task of locals) {
    if (args.signal.aborted) break;

    if (isLocalImageTaskId(task.taskId)) {
      try {
        await sleep(LOCAL_IMAGE_MOCK_DELAY_MS, args.signal);
      } catch {
        break;
      }
    }

    const resolved =
      takeLocalChartTaskResolution(task.taskId) ??
      takeLocalImageTaskResolution(task.taskId);
    if (!resolved) continue;
    const polledBlocks = normalizeTaskPollBody(resolved);
    if (!polledBlocks.length) continue;
    mergePolledBlocksIntoAssistantContent(
      args.assistantMsgId,
      polledBlocks,
      args.getAssistantMessage,
      args.upsertAssistantMessage,
    );
  }
}

/**
 * Poll async tool `taskId` endpoints until tasks complete or the request is aborted.
 *
 * **Never polls `local-chart:` ids** — those are client-side deferred chart renders, not server
 * tasks; they are filtered out before any `fetch` runs.
 *
 * **Poll response contract (frontend):** each GET should return JSON that parses as either a full
 * `UnifiedToolResponse` or a single `UnifiedToolItem` — use `normalizeTaskPollBody` so merges stay
 * aligned with `normalizeUnifiedToolResponse`.
 */
export async function pollAsyncToolTasksWhenEnabled(args: PollAsyncToolTasksArgs): Promise<void> {
  const config = useRuntimeConfig();
  const pub = config.public as Record<string, unknown>;
  const enabled = pub.asyncTaskPollEnabled === true || pub.asyncTaskPollEnabled === 'true';
  const remoteTasks = args.asyncTasks.filter((t) => !isLocalDeferredTaskId(t.taskId));
  if (!enabled || remoteTasks.length === 0) return;

  const configuredBase = String(pub.asyncTaskPollBaseUrl ?? '')
    .trim()
    .replace(/\/$/, '');
  const baseUrl = (configuredBase || args.chatApiBaseUrl || '').replace(/\/$/, '');
  const pathTemplate = String(pub.asyncTaskPollPath ?? '/v1/tasks/{{taskId}}');
  const token = String(pub.asyncTaskPollApiToken ?? args.apiToken ?? '').trim();
  if (!baseUrl) return;

  const pending = new Set(remoteTasks.map((t) => t.taskId));
  let backoffMs = 1000;
  const maxBackoffMs = 30_000;

  while (pending.size > 0 && !args.signal.aborted) {
    for (const taskId of [...pending]) {
      try {
        const path = interpolateTaskPath(pathTemplate, taskId);
        const url = `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
        const res = await fetch(url, {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          signal: args.signal,
        });
        if (!res.ok) {
          continue;
        }
        const body: unknown = await res.json();
        const polledBlocks = normalizeTaskPollBody(body);
        if (!polledBlocks.length) continue;

        const merged = mergePolledBlocksIntoAssistantContent(
          args.assistantMsgId,
          polledBlocks,
          args.getAssistantMessage,
          args.upsertAssistantMessage,
        );

        const block = merged.find((b) => readTaskIdFromBlock(b) === taskId);
        if (isTaskPollTerminal(block)) {
          pending.delete(taskId);
        }
      } catch {
        /* aborted or network — backoff below */
      }
    }

    if (pending.size === 0 || args.signal.aborted) break;
    try {
      await sleep(backoffMs, args.signal);
    } catch {
      break;
    }
    backoffMs = Math.min(maxBackoffMs, Math.floor(backoffMs * 1.5));
  }
}
