/**
 * Frontend-only async image simulation (`local-image:` task ids).
 * Resolves to [Lorem Picsum](https://picsum.photos/) URLs for dev/mock testing.
 */

import type { ImageToolData, UnifiedAsyncTool, UnifiedToolItem, UnifiedToolResponse } from '~/types/unified';
import { buildPicsumImageUrlFromPrompt } from './picsumImageUrl';

export const LOCAL_IMAGE_TASK_PREFIX = 'local-image:';

/** Brief delay so the image skeleton is visible during mock testing. */
export const LOCAL_IMAGE_MOCK_DELAY_MS = 1800;

const resolutions = new Map<string, UnifiedToolItem>();

export function isLocalImageTaskId(taskId: string | undefined): taskId is string {
  return typeof taskId === 'string' && taskId.startsWith(LOCAL_IMAGE_TASK_PREFIX);
}

export function makeLocalImageTaskId(requestId: string | undefined, toolIndex: number): string {
  const rid = typeof requestId === 'string' && requestId.trim() ? requestId.trim() : 'req';
  return `${LOCAL_IMAGE_TASK_PREFIX}${rid}-${toolIndex}`;
}

function isImageUnifiedTool(tool: UnifiedToolItem): boolean {
  const t = String(tool.type || '')
    .toLowerCase()
    .trim();
  return t === 'image' || t === 'visual' || t === 'picture';
}

function readImageUrl(data: unknown): string | undefined {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return undefined;
  const row = data as Record<string, unknown>;
  for (const key of ['imageUrl', 'url', 'src']) {
    const value = row[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
}

function readPrompt(data: unknown): string {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return '';
  const value = (data as Record<string, unknown>).prompt;
  return typeof value === 'string' ? value.trim() : '';
}

export function registerLocalImageTaskResolution(
  taskId: string,
  resolvedTool: UnifiedToolItem,
): void {
  if (!isLocalImageTaskId(taskId)) return;
  if (!resolutions.has(taskId)) resolutions.set(taskId, resolvedTool);
}

export function takeLocalImageTaskResolution(taskId: string): UnifiedToolItem | undefined {
  const row = resolutions.get(taskId);
  if (row) resolutions.delete(taskId);
  return row;
}

function buildResolvedImageTool(
  tool: UnifiedToolItem,
  taskId: string,
  imageUrl: string,
  prompt: string,
): UnifiedAsyncTool {
  const data = (tool.data ?? {}) as ImageToolData & Record<string, unknown>;
  return {
    ...tool,
    type: 'image',
    mode: 'async',
    status: 'success',
    taskId,
    data: {
      ...data,
      prompt: prompt || data.prompt,
      imageUrl,
      title: typeof data.title === 'string' ? data.title : 'Generated image',
    },
  };
}

/**
 * Registers picsum resolutions for mock `local-image:` pending tools (call before normalize/poll).
 */
export function bootstrapMockLocalImageTasks(envelope: UnifiedToolResponse): void {
  envelope.tools.forEach((tool, index) => {
    if (tool.mode !== 'async') return;
    const taskId = (tool as UnifiedAsyncTool).taskId;
    if (!isLocalImageTaskId(taskId)) return;
    if (resolutions.has(taskId)) return;

    const prompt = readPrompt(tool.data) || `mock-image-${index}`;
    const imageUrl = buildPicsumImageUrlFromPrompt(prompt, { width: 768, height: 512 });
    registerLocalImageTaskResolution(taskId, buildResolvedImageTool(tool, taskId, imageUrl, prompt));
  });
}

/**
 * Converts a successful sync image tool into a frontend-only deferred render (env-gated).
 */
export function prepareSyncImageToolForDeferredRender(
  tool: UnifiedToolItem,
  requestId: string | undefined,
  toolIndex: number,
): UnifiedToolItem {
  const config = useRuntimeConfig();
  const publicConfig = config.public as Record<string, unknown>;
  const enabled =
    publicConfig.localImageDeferEnabled === true ||
    publicConfig.localImageDeferEnabled === 'true';
  if (!enabled) return tool;
  if (!isImageUnifiedTool(tool)) return tool;
  if (tool.mode !== 'sync' || tool.status !== 'success') return tool;

  const imageUrl = readImageUrl(tool.data);
  if (!imageUrl) return tool;

  const taskId = makeLocalImageTaskId(requestId, toolIndex);
  const prompt = readPrompt(tool.data);
  registerLocalImageTaskResolution(
    taskId,
    buildResolvedImageTool(tool, taskId, imageUrl, prompt),
  );

  return {
    ...tool,
    mode: 'async',
    status: 'processing',
    taskId,
    data: {
      prompt: prompt || undefined,
      title:
        tool.data && typeof tool.data === 'object' && !Array.isArray(tool.data)
          ? (tool.data as Record<string, unknown>).title
          : undefined,
    },
  } as UnifiedToolItem;
}
