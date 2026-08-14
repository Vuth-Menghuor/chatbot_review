import type {
  MessageUiStatus,
  MessageBlock,
  ResponseMode,
  ResponseStatus,
  StreamingDeps,
  UnifiedToolResponse,
} from '~/types/message';
import {
  isLocalChartTaskId,
  normalizeUnifiedToolResponse,
  unifiedResponseToMarkerText,
} from '~/utils/tool';
import { blocksToMarkerText } from '~/utils/message';
import {
  isChatApiConfigured,
  handleNormalizedChatResponse,
  legacyChatResponseToMessageParts,
  ChatStreamEventError,
  normalizedBlockToMessageBlock,
  sendGdceChat,
  streamGdceChat,
} from '~/services/chat-api';
import { uploadImageFile } from '~/services/files-api';
import { useAuthStore } from '~/stores/auth.store';
import { useNotificationStore } from '~/stores/notification.store';
import { getImageUploadLimits, validateImageFile } from '~/utils/file/imageUpload';
import {
  pollAsyncToolTasksWhenEnabled,
  scheduleDeferredLocalChartTaskMerges,
} from '~/composables/chat/useAsyncToolTaskPoll';

type NormalizedChatMessageParts = NonNullable<ReturnType<typeof handleNormalizedChatResponse>>;

export function useChatStreaming(deps: StreamingDeps) {
  const notificationStore = useNotificationStore();

  function notifyResponseCompleted() {
    notificationStore.showToast({
      type: 'success',
      title: 'Response completed',
      message: 'ChatGDCE finished responding.',
      notificationId: 'responseCompleted',
    });
  }

  function responseStatusToUiStatus(status: ResponseStatus): MessageUiStatus {
    return status === 'failed' ? 'error' : 'completed';
  }

  function coerceResponseStatus(value: unknown, fallback: ResponseStatus = 'processing'): ResponseStatus {
    const status = String(value || '').toLowerCase();
    if (status === 'completed' || status === 'success' || status === 'done') return 'completed';
    if (status === 'failed' || status === 'error' || status === 'cancelled') return 'failed';
    if (status === 'partial') return 'partial';
    if (status === 'clarification_required') return 'clarification_required';
    if (status === 'pending') return 'pending';
    return fallback;
  }

  function responseStatusToStreamingUiStatus(status: ResponseStatus): MessageUiStatus {
    if (status === 'failed') return 'error';
    if (status === 'completed' || status === 'partial' || status === 'clarification_required') {
      return 'completed';
    }
    return 'streaming';
  }

  function coerceResponseMode(value: unknown, fallback: ResponseMode = 'stream'): ResponseMode {
    const mode = String(value || '').toLowerCase();
    if (mode === 'sync' || mode === 'async' || mode === 'stream') return mode;
    return fallback;
  }

  function progressText(value: unknown, fallback: string) {
    return typeof value === 'string' && value.trim() ? value.trim() : fallback;
  }

  function isCalculatorRequest(message: string) {
    const normalized = message.toLowerCase();
    return (
      /\b(calculate|calculation)\b/.test(normalized) &&
      /\b(import|tax|duty|cif)\b/.test(normalized)
    );
  }

  function isTradeChartRequest(message: string) {
    const normalized = message.toLowerCase();
    const requestsChart = /\b(chart|graph|pie|bar|line|visuali[sz]e|plot)\b/.test(normalized);
    const requestsTradeData = /\b(trade|partner|transport|import partners|export partners|sea transport)\b/.test(normalized);
    return requestsChart && requestsTradeData;
  }

  function streamingMarkdownBlock(messageId: string, content: string) {
    return [{
      id: `${messageId}-streaming-markdown`,
      type: 'markdown' as const,
      content,
      isComplete: false,
    }];
  }

  function streamErrorBlock(messageId: string, detail: string) {
    return [{
      id: `${messageId}-stream-error`,
      type: 'error' as const,
      content: {
        title: 'Response unavailable',
        message: detail,
      },
      isComplete: true,
    }];
  }

  function blocksToStreamingText(blocks: MessageBlock[]) {
    return blocksToMarkerText(blocks);
  }

  function hasRenderableFinalContent(parts: { content?: string; blocks?: unknown[] } | null) {
    if (!parts) return false;
    if (parts.blocks?.length) return parts.blocks.some(isRenderableFinalBlock);
    return Boolean(parts.content?.trim());
  }

  function isRenderableFinalBlock(block: unknown) {
    if (!block || typeof block !== 'object' || Array.isArray(block)) return false;
    const record = block as Record<string, unknown>;
    const type = String(record.type ?? '').toLowerCase();
    const content = record.content;
    if (type === 'markdown' || type === 'reasoning' || type === 'code' || type === 'tool_output') {
      return typeof content === 'string' && content.trim().length > 0;
    }
    if (type === 'suggestions') {
      return Array.isArray(content) && content.length > 0;
    }
    if (type === 'error') {
      if (typeof content === 'string') return content.trim().length > 0;
      if (content && typeof content === 'object' && !Array.isArray(content)) {
        const message = (content as Record<string, unknown>).message;
        return typeof message === 'string' && message.trim().length > 0;
      }
      return false;
    }
    return true;
  }

  function completedStreamingMarkdownBlock(messageId: string, content: string) {
    return [{
      id: `${messageId}-streaming-markdown`,
      type: 'markdown' as const,
      content,
      isComplete: true,
    }];
  }

  function shouldRevealFinalBlocksProgressively(
    parts: NormalizedChatMessageParts,
    streamedContent: string,
  ) {
    if (parts.blocks.length < 2) return false;
    return parts.blocks.some((block) => block.type !== 'markdown');
  }

  function finalBlockRevealDelay(block: MessageBlock) {
    const rawDelay = deps.getUiBlockDelay(String(block.type));
    if (rawDelay <= 0) return 0;
    return Math.min(Math.max(rawDelay, 180), 420);
  }

  /**
   * Keep component keys stable when an in-progress stream is replaced by the
   * authoritative `done` payload. The final payload always supplies content;
   * only the prior block identity is retained to avoid a remount/fade flash.
   */
  function preserveRenderedBlockIds(assistantMsgId: string, blocks: MessageBlock[]) {
    const available = [...(deps.getAssistantMessage(assistantMsgId)?.blocks ?? [])];
    return blocks.map((block) => {
      const existingIndex = available.findIndex((existing) => existing.type === block.type);
      if (existingIndex < 0) return block;
      const [existing] = available.splice(existingIndex, 1);
      return { ...block, id: existing.id };
    });
  }

  function withBlockCompletion(block: MessageBlock, isComplete: boolean) {
    return {
      ...block,
      isComplete,
    };
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value && typeof value === 'object' && !Array.isArray(value));
  }

  function isTableBlock(block: MessageBlock) {
    if (block.type !== 'table' || !isRecord(block.content)) return false;
    return Array.isArray(block.content.columns) && Array.isArray(block.content.rows);
  }

  function tableRevealDelay(block: MessageBlock, phase: 'shell' | 'cell' | 'row') {
    const rawDelay = deps.getUiBlockDelay(String(block.type));
    if (rawDelay <= 0) return 0;
    if (phase === 'shell') return 120;
    if (phase === 'cell') return 70;
    return 130;
  }

  function tableBlockWithRows(block: MessageBlock, rows: Record<string, unknown>[], isComplete: boolean) {
    if (!isRecord(block.content)) return withBlockCompletion(block, isComplete);
    return {
      ...block,
      content: {
        ...block.content,
        rows,
      },
      isComplete,
    };
  }

  function tableRowSnapshots(
    block: MessageBlock,
  ): Array<{ rows: Record<string, unknown>[]; phase: 'cell' | 'row'; isComplete: boolean }> {
    if (!isRecord(block.content)) return [];
    const columns = Array.isArray(block.content.columns) ? block.content.columns : [];
    const rows = Array.isArray(block.content.rows) ? block.content.rows : [];
    const columnKeys = columns
      .map((column) => (isRecord(column) ? String(column.key ?? '') : ''))
      .filter(Boolean);
    const snapshots: Array<{ rows: Record<string, unknown>[]; phase: 'cell' | 'row'; isComplete: boolean }> = [];
    const completedRows: Record<string, unknown>[] = [];

    rows.forEach((rawRow, rowIndex) => {
      const row = isRecord(rawRow) ? rawRow : {};
      const keys = columnKeys.length ? columnKeys : Object.keys(row);
      if (!keys.length) {
        completedRows.push(row);
        snapshots.push({
          rows: [...completedRows],
          phase: 'row',
          isComplete: rowIndex === rows.length - 1,
        });
        return;
      }

      keys.forEach((key, cellIndex) => {
        const partialRow = keys.reduce<Record<string, unknown>>((acc, currentKey, currentIndex) => {
          acc[currentKey] = currentIndex <= cellIndex ? row[currentKey] : '';
          return acc;
        }, {});
        snapshots.push({
          rows: [...completedRows, partialRow],
          phase: cellIndex === keys.length - 1 ? 'row' : 'cell',
          isComplete: rowIndex === rows.length - 1 && cellIndex === keys.length - 1,
        });
      });
      completedRows.push(row);
    });

    return snapshots;
  }

  function shouldStreamFinalMarkdown(parts: NormalizedChatMessageParts, streamedContent: string) {
    if (streamedContent.trim()) return false;
    if (parts.blocks.length !== 1) return false;
    const [block] = parts.blocks;
    return block.type === 'markdown' && typeof block.content === 'string' && block.content.trim().length > 0;
  }

  function markdownFallbackChunks(content: string) {
    const text = content.trim();
    if (text.length <= 36) return text.match(/.{1,2}/g) ?? [text];

    const pieces = text.match(/\S+\s*/g) ?? [text];
    const chunks: string[] = [];
    for (let index = 0; index < pieces.length; index += 2) {
      chunks.push(`${pieces[index] ?? ''}${pieces[index + 1] ?? ''}`);
    }
    return chunks.filter(Boolean);
  }

  function markdownFallbackDelay(chunk: string) {
    const rawDelay = deps.typing.getPiecePause(chunk);
    const minimumDelay = chunk.trim().length <= 2 ? 85 : 60;
    return Math.max(rawDelay, minimumDelay);
  }

  function visibleDeltaDelay(chunk: string) {
    const rawDelay = deps.typing.getPiecePause(chunk);
    const trimmedLength = chunk.trim().length;
    if (trimmedLength <= 4) return Math.max(rawDelay, 45);
    if (trimmedLength <= 16) return Math.max(rawDelay, 65);
    return Math.max(rawDelay, 90);
  }

  function visibleDeltaChunks(content: string) {
    if (!content) return [];
    if (content.length <= 12) return [content];
    if (content.length <= 180) return content.match(/.{1,4}/g) ?? [content];

    const pieces = content.match(/\S+\s*/g) ?? [content];
    const chunks: string[] = [];
    for (let index = 0; index < pieces.length; index += 2) {
      chunks.push(`${pieces[index] ?? ''}${pieces[index + 1] ?? ''}`);
    }
    return chunks.filter(Boolean);
  }

  async function streamFinalMarkdownFallback(
    assistantMsgId: string,
    parts: NormalizedChatMessageParts,
    normalizedDone: Record<string, unknown> | null,
    startedAt: number,
  ) {
    const block = parts.blocks[0];
    const finalContent = typeof block.content === 'string' ? block.content.trim() : parts.content.trim();
    let visibleContent = '';

    for (const chunk of markdownFallbackChunks(finalContent)) {
      if (deps.stopStreaming.value || deps.streamController.value?.signal.aborted) return;
      visibleContent = `${visibleContent}${chunk}`;
      deps.currentRenderType.value = 'markdown';
      deps.upsertAssistantMessage(assistantMsgId, visibleContent, {
        blocks: streamingMarkdownBlock(assistantMsgId, visibleContent),
        sources: parts.sources,
        generationDurationMs: parts.latencyMs ?? Date.now() - startedAt,
        status: 'streaming',
        responseStatus: 'processing',
        responseMode: 'stream',
        progressStage: 'streaming',
        progressMessage: 'Streaming response...',
        streamingContent: visibleContent,
        normalizedResponse: normalizedDone,
        error: null,
        coverage: parts.coverage,
        confidence: parts.confidence,
      });
      await deps.typing.sleep(markdownFallbackDelay(chunk));
    }

    if (deps.stopStreaming.value || deps.streamController.value?.signal.aborted) return;
    deps.upsertAssistantMessage(assistantMsgId, finalContent, {
      blocks: completedStreamingMarkdownBlock(assistantMsgId, finalContent),
      sources: parts.sources,
      generationDurationMs: parts.latencyMs ?? Date.now() - startedAt,
      status: responseStatusToUiStatus(parts.status),
      responseStatus: parts.status,
      responseMode: 'stream',
      progressStage: 'completed',
      progressMessage: parts.status === 'completed' ? 'Response completed.' : 'Response finished.',
      streamingContent: '',
      normalizedResponse: normalizedDone,
      error: null,
      coverage: parts.coverage,
      confidence: parts.confidence,
    });
  }

  function revealProgressMeta(
    assistantMsgId: string,
    parts: NormalizedChatMessageParts,
    visibleBlocks: MessageBlock[],
    normalizedDone: Record<string, unknown> | null,
    streamedContent: string,
    startedAt: number,
    isFinal: boolean,
  ) {
    deps.upsertAssistantMessage(assistantMsgId, parts.content, {
      blocks: visibleBlocks,
      sources: parts.sources,
      generationDurationMs: parts.latencyMs ?? Date.now() - startedAt,
      status: isFinal ? responseStatusToUiStatus(parts.status) : 'streaming',
      responseStatus: isFinal ? parts.status : 'processing',
      responseMode: 'stream',
      progressStage: isFinal ? 'completed' : 'rendering',
      progressMessage: isFinal
        ? (parts.status === 'completed' ? 'Response completed.' : 'Response finished.')
        : 'Formatting response...',
      streamingContent: isFinal ? '' : streamedContent,
      normalizedResponse: normalizedDone,
      error: null,
      coverage: parts.coverage,
      confidence: parts.confidence,
    });
  }

  async function revealFinalBlocksProgressively(
    assistantMsgId: string,
    parts: NormalizedChatMessageParts,
    normalizedDone: Record<string, unknown> | null,
    streamedContent: string,
    startedAt: number,
  ) {
    const revealBlocks = preserveRenderedBlockIds(assistantMsgId, parts.blocks);

    for (let index = 0; index < revealBlocks.length; index += 1) {
      if (deps.stopStreaming.value || deps.streamController.value?.signal.aborted) return;

      const block = revealBlocks[index];
      const isFinalBlock = index === revealBlocks.length - 1;
      const completedBlocks = revealBlocks.slice(0, index);
      deps.currentRenderType.value = String(block.type);

      if (block.type !== 'markdown') {
        const formattingBlock = isTableBlock(block)
          ? tableBlockWithRows(block, [], false)
          : withBlockCompletion(block, false);
        revealProgressMeta(
          assistantMsgId,
          parts,
          [...completedBlocks, formattingBlock],
          normalizedDone,
          streamedContent,
          startedAt,
          false,
        );
        await deps.typing.sleep(isTableBlock(block) ? tableRevealDelay(block, 'shell') : finalBlockRevealDelay(block));
        if (deps.stopStreaming.value || deps.streamController.value?.signal.aborted) return;
      }

      if (isTableBlock(block)) {
        const snapshots = tableRowSnapshots(block);
        for (const snapshot of snapshots) {
          const tableBlock = tableBlockWithRows(block, snapshot.rows, snapshot.isComplete);
          const isFinalSnapshot = isFinalBlock && snapshot.isComplete;
          revealProgressMeta(
            assistantMsgId,
            parts,
            [...completedBlocks, tableBlock],
            normalizedDone,
            streamedContent,
            startedAt,
            isFinalSnapshot,
          );
          if (!snapshot.isComplete) {
            await deps.typing.sleep(tableRevealDelay(block, snapshot.phase));
            if (deps.stopStreaming.value || deps.streamController.value?.signal.aborted) return;
          }
        }
        continue;
      }

      if (block.type === 'markdown' && typeof block.content === 'string') {
        let visibleContent = '';
        const chunks = markdownFallbackChunks(block.content);
        for (const chunk of chunks) {
          if (deps.stopStreaming.value || deps.streamController.value?.signal.aborted) return;
          visibleContent = `${visibleContent}${chunk}`;
          revealProgressMeta(
            assistantMsgId,
            parts,
            [...completedBlocks, withBlockCompletion({ ...block, content: visibleContent }, false)],
            normalizedDone,
            streamedContent,
            startedAt,
            false,
          );
          await deps.typing.sleep(markdownFallbackDelay(chunk));
        }
      }

      revealProgressMeta(
        assistantMsgId,
        parts,
        [...completedBlocks, withBlockCompletion(block, true)],
        normalizedDone,
        streamedContent,
        startedAt,
        isFinalBlock,
      );
    }
  }

  function maybeStartAsyncTaskPoll(
    unified: UnifiedToolResponse,
    assistantMsgId: string,
    signal: AbortSignal,
  ) {
    const norm = normalizeUnifiedToolResponse(unified);
    if (!norm.asyncTasks.length) return;

    const mergeDeps = {
      assistantMsgId,
      signal,
      getAssistantMessage: deps.getAssistantMessage,
      upsertAssistantMessage: deps.upsertAssistantMessage,
    };

    void scheduleDeferredLocalChartTaskMerges({ ...mergeDeps, asyncTasks: norm.asyncTasks });

    const remoteTasks = norm.asyncTasks.filter((t) => !isLocalChartTaskId(t.taskId));
    if (remoteTasks.length && deps.chatApi) {
      void pollAsyncToolTasksWhenEnabled({
        ...mergeDeps,
        asyncTasks: remoteTasks,
        chatApiBaseUrl: deps.chatApi.baseUrl,
        apiToken: deps.chatApi.apiToken,
      });
    }
  }

  async function prepareAttachments(files: unknown[] | undefined) {
    const runtimeConfig = useRuntimeConfig();
    const limits = getImageUploadLimits(
      runtimeConfig.public.allowedImageTypes as string | string[],
      runtimeConfig.public.maxImageSizeMb as number | string,
    );
    const authStore = useAuthStore();
    const token = await authStore.getValidAccessToken();
    if (!token) throw new Error('Not authenticated. Please sign in.');

    const attachments: unknown[] = [];
    for (const item of files ?? []) {
      if (item instanceof File) {
        const validationError = validateImageFile(item, limits);
        if (validationError) throw new Error(validationError);

        const uploaded = await uploadImageFile(deps.chatApi!.baseUrl, token, item);
        attachments.push({
          file_id: uploaded.file_id,
          name: item.name,
          mime_type: item.type,
          size: item.size,
          url: uploaded.url,
          object_key: uploaded.object_key,
          bucket: uploaded.bucket,
          status: uploaded.status,
        });
        continue;
      }
      attachments.push(item);
    }
    return attachments;
  }

  async function streamFromChatApi(
    text: string,
    files: unknown[] | undefined,
    assistantMsgId: string,
    context?: Record<string, unknown>,
  ) {
    if (!deps.chatApi || !isChatApiConfigured(deps.chatApi)) {
      throw new Error('Chat API is not configured');
    }

    const transport = deps.chatApi.transport ?? 'gdce';
    if (transport !== 'gdce') {
      throw new Error('Only the GDCE API-layer transport is enabled in this build');
    }

    const controller = new AbortController();
    deps.streamController.value = controller;
    deps.currentRenderType.value = 'thinking';
    const startedAt = Date.now();
    let currentContent = '';
    let receivedDeltaContent = '';
    let normalizedDone: Record<string, unknown> | null = null;
    let firstDelta = true;
    let streamFailed = false;
    const streamedBlocks: MessageBlock[] = [];
    let deltaRenderTail: Promise<void> = Promise.resolve();
    const calculatorRequest = isCalculatorRequest(text);
    const tradeChartRequest = isTradeChartRequest(text);
    const attachments = await prepareAttachments(files);

    try {
      if (tradeChartRequest) {
        deps.currentRenderType.value = 'thinking';
        deps.upsertAssistantMessage(assistantMsgId, '', {
          status: 'streaming',
          responseStatus: 'processing',
          blocks: [],
          responseMode: 'stream',
          progressStage: 'starting',
          progressMessage: 'Preparing trade report...',
          streamingContent: '',
          error: null,
        });
        normalizedDone = await sendGdceChat({
          baseUrl: deps.chatApi.baseUrl,
          apiToken: deps.chatApi.apiToken,
          message: text,
          chatId: deps.chatId,
          projectId: deps.projectId,
          attachments,
          presentation: presentationPreferenceFromMessage(text),
          context,
          signal: controller.signal,
        });
      } else {
      await streamGdceChat({
        baseUrl: deps.chatApi.baseUrl,
        apiToken: deps.chatApi.apiToken,
        message: text,
        chatId: deps.chatId,
        projectId: deps.projectId,
        attachments,
        presentation: presentationPreferenceFromMessage(text),
        context,
        signal: controller.signal,
        onStart: (data) => {
          if (deps.stopStreaming.value) return;
          deps.currentRenderType.value = 'response';
          const responseStatus = coerceResponseStatus(data.status);
          const responseMode = coerceResponseMode(data.mode);
          deps.upsertAssistantMessage(assistantMsgId, '', {
            status: responseStatusToStreamingUiStatus(responseStatus),
            responseStatus,
            blocks: [],
            requestId: typeof data.request_id === 'string' ? data.request_id : undefined,
            chatId: typeof data.chat_id === 'string' ? data.chat_id : undefined,
            responseMode,
            progressStage: 'starting',
            progressMessage: responseMode === 'stream' ? 'Starting response stream...' : 'Starting response...',
            streamingContent: '',
            error: null,
          });
        },
        onProgress: (data) => {
          if (deps.stopStreaming.value) return;
          const responseStatus = coerceResponseStatus(data.status);
          const responseMode = coerceResponseMode(data.mode);
          deps.currentRenderType.value = progressText(data.stage, 'response');
          const existing = deps.getAssistantMessage(assistantMsgId);
          const existingContent = existing?.content ?? currentContent;
          deps.upsertAssistantMessage(assistantMsgId, existingContent, {
            status: responseStatusToStreamingUiStatus(responseStatus),
            responseStatus,
            blocks: existing?.blocks ?? (existingContent ? streamingMarkdownBlock(assistantMsgId, existingContent) : []),
            requestId: typeof data.request_id === 'string' ? data.request_id : undefined,
            chatId: typeof data.chat_id === 'string' ? data.chat_id : undefined,
            responseMode,
            progressStage: progressText(data.stage, 'processing'),
            progressMessage: progressText(data.message, 'Processing request...'),
            streamingContent: currentContent,
            error: null,
          });
        },
        onDelta: (content) => {
          receivedDeltaContent = `${receivedDeltaContent}${content}`;
          // Do not make the SSE reader wait for cosmetic typing delays. Incoming
          // events remain ordered in this queue and are flushed before `done` is
          // applied below.
          deltaRenderTail = deltaRenderTail.then(async () => {
            if (deps.stopStreaming.value || streamFailed || streamedBlocks.length) return;
            // Calculator deltas are an upstream progress narrative, while the
            // authoritative answer is delivered as summary/table/detail blocks.
            // Do not show that narrative as a second, conflicting calculation.
            if (calculatorRequest) {
              deps.currentRenderType.value = 'calculator';
              deps.upsertAssistantMessage(assistantMsgId, '', {
                status: 'streaming',
                responseStatus: 'processing',
                blocks: [],
                responseMode: 'stream',
                progressStage: 'streaming',
                progressMessage: 'Calculating import tax...',
                streamingContent: '',
                error: null,
              });
              return;
            }
            if (firstDelta) {
              firstDelta = false;
              deps.currentRenderType.value = 'markdown';
            }
            const existing = deps.getAssistantMessage(assistantMsgId);
            currentContent = existing?.content ?? currentContent;

            for (const chunk of visibleDeltaChunks(content)) {
              if (deps.stopStreaming.value || streamFailed || controller.signal.aborted) return;
              currentContent = `${currentContent}${chunk}`;
              deps.upsertAssistantMessage(assistantMsgId, currentContent, {
                status: 'streaming',
                responseStatus: 'processing',
                blocks: streamingMarkdownBlock(assistantMsgId, currentContent),
                responseMode: 'stream',
                progressStage: 'streaming',
                progressMessage: 'Streaming response...',
                streamingContent: currentContent,
              });
              await deps.typing.sleep(visibleDeltaDelay(chunk));
            }
          });
        },
        onBlock: async (block) => {
          await deltaRenderTail;
          if (deps.stopStreaming.value) return;
          const index = streamedBlocks.length;
          const messageBlock = normalizedBlockToMessageBlock(block, `${assistantMsgId}-stream-block-${index}`);
          deps.currentRenderType.value = String(messageBlock.type);

          // Some upstreams send the answer first as `delta` events and then
          // repeat it as the first complete markdown block. Keep the already
          // visible delta text and use this block only as its confirmation;
          // streaming the same markdown again looks like a second response.
          if (
            !streamedBlocks.length &&
            receivedDeltaContent &&
            !calculatorRequest &&
            messageBlock.type === 'markdown' &&
            typeof messageBlock.content === 'string'
          ) {
            const confirmedContent = currentContent || receivedDeltaContent;
            streamedBlocks.push({
              ...messageBlock,
              id: `${assistantMsgId}-streaming-markdown`,
              content: confirmedContent,
              isComplete: true,
            });
            deps.upsertAssistantMessage(assistantMsgId, blocksToStreamingText(streamedBlocks), {
              status: 'streaming',
              responseStatus: 'processing',
              blocks: [...streamedBlocks],
              responseMode: 'stream',
              progressStage: 'rendering',
              progressMessage: 'Formatting response...',
              streamingContent: '',
              error: null,
            });
            return;
          }

          if (messageBlock.type === 'markdown' && typeof messageBlock.content === 'string') {
            let visibleContent = '';
            streamedBlocks.push(withBlockCompletion({ ...messageBlock, content: visibleContent }, false));

            for (const chunk of markdownFallbackChunks(messageBlock.content)) {
              if (deps.stopStreaming.value || controller.signal.aborted) return;
              visibleContent = `${visibleContent}${chunk}`;
              streamedBlocks[index] = withBlockCompletion({ ...messageBlock, content: visibleContent }, false);
              deps.upsertAssistantMessage(assistantMsgId, blocksToStreamingText(streamedBlocks), {
                status: 'streaming',
                responseStatus: 'processing',
                blocks: [...streamedBlocks],
                responseMode: 'stream',
                progressStage: 'streaming',
                progressMessage: 'Streaming response...',
                streamingContent: visibleContent,
                error: null,
              });
              await deps.typing.sleep(markdownFallbackDelay(chunk));
            }

            if (deps.stopStreaming.value || controller.signal.aborted) return;
            streamedBlocks[index] = withBlockCompletion(messageBlock, true);
            deps.upsertAssistantMessage(assistantMsgId, blocksToStreamingText(streamedBlocks), {
              status: 'streaming',
              responseStatus: 'processing',
              blocks: [...streamedBlocks],
              responseMode: 'stream',
              progressStage: 'rendering',
              progressMessage: 'Formatting response...',
              streamingContent: '',
              error: null,
            });
            return;
          }

          streamedBlocks.push(withBlockCompletion(messageBlock, false));
          deps.upsertAssistantMessage(assistantMsgId, blocksToStreamingText(streamedBlocks), {
            status: 'streaming',
            responseStatus: 'processing',
            blocks: [...streamedBlocks],
            responseMode: 'stream',
            progressStage: 'rendering',
            progressMessage: 'Formatting response...',
            streamingContent: '',
            error: null,
          });
          await deps.typing.sleep(finalBlockRevealDelay(messageBlock));
          if (deps.stopStreaming.value || controller.signal.aborted) return;
          streamedBlocks[index] = withBlockCompletion(messageBlock, true);
          deps.upsertAssistantMessage(assistantMsgId, blocksToStreamingText(streamedBlocks), {
            status: 'streaming',
            responseStatus: 'processing',
            blocks: [...streamedBlocks],
            responseMode: 'stream',
            progressStage: 'rendering',
            progressMessage: 'Formatting response...',
            streamingContent: '',
            error: null,
          });
        },
        onDone: (data) => {
          normalizedDone = data;
        },
        onError: (data) => {
          streamFailed = true;
          const detail = String(data.detail ?? 'Chat stream failed');
          const existing = deps.getAssistantMessage(assistantMsgId);
          const preservedContent = receivedDeltaContent || existing?.content || currentContent;
          const nextContent = preservedContent || detail;
          deps.upsertAssistantMessage(assistantMsgId, nextContent, {
            status: 'error',
            responseStatus: 'failed',
            blocks: preservedContent
              ? streamingMarkdownBlock(assistantMsgId, preservedContent)
              : streamErrorBlock(assistantMsgId, detail),
            responseMode: 'stream',
            progressStage: 'failed',
            progressMessage: detail,
            streamingContent: preservedContent,
            error: detail,
          });
        },
      });
      }
    } catch (error) {
      if (error instanceof ChatStreamEventError) return;
      throw error;
    }

    await deltaRenderTail;
    if (deps.stopStreaming.value || controller.signal.aborted) return;
    const normalizedParts = handleNormalizedChatResponse(normalizedDone, assistantMsgId);
    if (normalizedParts) {
      // `block` events have already been rendered in order. Applying the final
      // payload once makes it authoritative without replaying those blocks and
      // causing a visible completion flash.
      if (streamedBlocks.length) {
        deps.upsertAssistantMessage(assistantMsgId, normalizedParts.content, {
          blocks: preserveRenderedBlockIds(assistantMsgId, normalizedParts.blocks),
          sources: normalizedParts.sources,
          generationDurationMs: normalizedParts.latencyMs ?? Date.now() - startedAt,
          status: responseStatusToUiStatus(normalizedParts.status),
          responseStatus: normalizedParts.status,
          responseMode: 'stream',
          progressStage: 'completed',
          progressMessage: normalizedParts.status === 'completed' ? 'Response completed.' : 'Response finished.',
          streamingContent: '',
          normalizedResponse: normalizedDone,
          error: null,
          coverage: normalizedParts.coverage,
          confidence: normalizedParts.confidence,
        });
        if (normalizedParts.status === 'completed') notifyResponseCompleted();
        return;
      }
      if (!hasRenderableFinalContent(normalizedParts) && currentContent.trim()) {
        const finalContent = currentContent.trim();
        deps.upsertAssistantMessage(assistantMsgId, finalContent, {
          blocks: completedStreamingMarkdownBlock(assistantMsgId, finalContent),
          sources: normalizedParts.sources,
          generationDurationMs: normalizedParts.latencyMs ?? Date.now() - startedAt,
          status: responseStatusToUiStatus(normalizedParts.status),
          responseStatus: normalizedParts.status,
          responseMode: 'stream',
          progressStage: 'completed',
          progressMessage: normalizedParts.status === 'completed' ? 'Response completed.' : 'Response finished.',
          streamingContent: '',
          normalizedResponse: normalizedDone,
          error: null,
          coverage: normalizedParts.coverage,
          confidence: normalizedParts.confidence,
        });
        if (normalizedParts.status === 'completed') notifyResponseCompleted();
        return;
      }
      if (shouldStreamFinalMarkdown(normalizedParts, currentContent)) {
        await streamFinalMarkdownFallback(assistantMsgId, normalizedParts, normalizedDone, startedAt);
        if (normalizedParts.status === 'completed') notifyResponseCompleted();
        return;
      }
      if (shouldRevealFinalBlocksProgressively(normalizedParts, currentContent)) {
        await revealFinalBlocksProgressively(
          assistantMsgId,
          normalizedParts,
          normalizedDone,
          currentContent,
          startedAt,
        );
        if (normalizedParts.status === 'completed') notifyResponseCompleted();
        return;
      }
      deps.upsertAssistantMessage(assistantMsgId, normalizedParts.content, {
        blocks: preserveRenderedBlockIds(assistantMsgId, normalizedParts.blocks),
        sources: normalizedParts.sources,
        generationDurationMs: normalizedParts.latencyMs ?? Date.now() - startedAt,
        status: responseStatusToUiStatus(normalizedParts.status),
        responseStatus: normalizedParts.status,
        responseMode: 'stream',
        progressStage: 'completed',
        progressMessage: normalizedParts.status === 'completed' ? 'Response completed.' : 'Response finished.',
        streamingContent: '',
        normalizedResponse: normalizedDone,
        error: null,
        coverage: normalizedParts.coverage,
        confidence: normalizedParts.confidence,
      });
      if (normalizedParts.status === 'completed') notifyResponseCompleted();
      return;
    }
    const legacyParts = legacyChatResponseToMessageParts(normalizedDone, assistantMsgId);
    if (legacyParts) {
      deps.upsertAssistantMessage(assistantMsgId, legacyParts.content || currentContent, {
        blocks: preserveRenderedBlockIds(assistantMsgId, legacyParts.blocks),
        sources: legacyParts.sources,
        generationDurationMs: Date.now() - startedAt,
        status: responseStatusToUiStatus(legacyParts.status),
        responseStatus: legacyParts.status,
        responseMode: 'stream',
        progressStage: 'completed',
        progressMessage: legacyParts.status === 'completed' ? 'Response completed.' : 'Response finished.',
        streamingContent: '',
        error: null,
        coverage: legacyParts.coverage,
        confidence: legacyParts.confidence,
      });
      if (legacyParts.status === 'completed') notifyResponseCompleted();
      return;
    }

    const unified = {
      requestId: assistantMsgId,
      mode: 'sync',
      status: 'success',
      tools: [],
    } as UnifiedToolResponse;
    const markerText = unifiedResponseToMarkerText(unified);
    const fallbackContent = markerText || currentContent;
    deps.upsertAssistantMessage(assistantMsgId, fallbackContent, {
      generationDurationMs: Date.now() - startedAt,
      status: fallbackContent.trim() ? 'completed' : 'error',
      responseStatus: fallbackContent.trim() ? 'completed' : 'failed',
      responseMode: 'stream',
      progressStage: 'completed',
      progressMessage: fallbackContent.trim()
        ? 'Response completed.'
        : 'Response stream ended before a final answer was received.',
      streamingContent: '',
      blocks: fallbackContent.trim()
        ? completedStreamingMarkdownBlock(assistantMsgId, fallbackContent)
        : streamErrorBlock(assistantMsgId, 'Response stream ended before a final answer was received.'),
      error: fallbackContent.trim() ? null : 'Response stream ended before a final answer was received.',
    });
    if (fallbackContent.trim()) notifyResponseCompleted();
    maybeStartAsyncTaskPoll(unified, assistantMsgId, controller.signal);
  }

  return { streamFromChatApi };
}

export function presentationPreferenceFromMessage(message: string) {
  const normalized = message.toLowerCase();
  const preferredBlocks: string[] = [];
  if (/\b(table|tabular)\b/.test(normalized)) preferredBlocks.push('table');
  if (/\b(card|prediction)\b/.test(normalized)) preferredBlocks.push('prediction');
  if (/\b(report)\b/.test(normalized)) preferredBlocks.push('report');
  if (/\b(chart|graph|visuali[sz]e|plot)\b/.test(normalized)) preferredBlocks.push('chart');
  if (!preferredBlocks.length) return undefined;
  return {
    preferred_blocks: [...new Set(preferredBlocks)],
    fallback: 'markdown' as const,
  };
}
