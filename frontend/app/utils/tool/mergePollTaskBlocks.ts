import type { MessageBlock } from '~/types/message';

function readTaskId(b: MessageBlock): string | undefined {
  const c = b.content;
  if (c && typeof c === 'object' && !Array.isArray(c)) {
    const t = (c as Record<string, unknown>).taskId;
    if (typeof t === 'string' && t.trim()) return t.trim();
  }
  const mt = b.meta?.tool;
  if (mt && typeof mt === 'object' && !Array.isArray(mt)) {
    const t = (mt as Record<string, unknown>).taskId;
    if (typeof t === 'string' && t.trim()) return t.trim();
  }
  return undefined;
}

export function readTaskIdFromBlock(b: MessageBlock): string | undefined {
  return readTaskId(b);
}

/** True when merged block content shows a finished async tool lifecycle. */
export function isTaskPollTerminal(block: MessageBlock | undefined): boolean {
  if (!block) return false;
  const c = block.content;
  if (!c || typeof c !== 'object' || Array.isArray(c)) return false;
  const o = c as Record<string, unknown>;
  const ts = o.toolStatus;
  if (ts === 'success' || ts === 'error' || ts === 'cancelled') return true;
  const w = o.status;
  if (w === 'completed' || w === 'error') return true;
  return false;
}

function readToolKey(b: MessageBlock): string | undefined {
  const c = b.content;
  if (c && typeof c === 'object' && !Array.isArray(c)) {
    const tn = (c as Record<string, unknown>).toolName;
    const typ = (c as Record<string, unknown>).type;
    if (typeof tn === 'string' && typeof typ === 'string') return `${tn}:${typ}`;
  }
  const m = b.meta?.tool as Record<string, unknown> | undefined;
  if (m && typeof m.toolName === 'string' && typeof m.type === 'string')
    return `${m.toolName}:${m.type}`;
  return undefined;
}

function mergeTwoBlocks(prev: MessageBlock, next: MessageBlock): MessageBlock {
  const pc = prev.content;
  const nc = next.content;
  let content: unknown = nc;
  if (
    pc &&
    nc &&
    typeof pc === 'object' &&
    typeof nc === 'object' &&
    !Array.isArray(pc) &&
    !Array.isArray(nc)
  ) {
    content = { ...(pc as Record<string, unknown>), ...(nc as Record<string, unknown>) };
  } else if (typeof pc === 'string' && typeof nc === 'string') {
    content = nc.length >= pc.length ? nc : pc;
  }
  return {
    ...prev,
    ...next,
    content,
    meta:
      next.meta && typeof next.meta === 'object' && Object.keys(next.meta).length
        ? { ...prev.meta, ...next.meta }
        : prev.meta,
    isComplete: next.isComplete !== undefined ? next.isComplete : prev.isComplete,
  };
}

/** Apply poll-normalized blocks onto the current assistant blocks (match by `taskId`, else `toolName`+`type`). */
export function mergePolledBlocksIntoBlocks(
  existing: MessageBlock[],
  polled: MessageBlock[],
): MessageBlock[] {
  const out = existing.map((b) => ({ ...b }));
  for (const nb of polled) {
    const tid = readTaskId(nb);
    let idx = tid ? out.findIndex((b) => readTaskId(b) === tid) : -1;
    if (idx < 0) {
      const key = readToolKey(nb);
      if (key) idx = out.findIndex((b) => readToolKey(b) === key);
    }
    if (idx >= 0) {
      out[idx] = mergeTwoBlocks(out[idx]!, nb);
    }
  }
  return out;
}
