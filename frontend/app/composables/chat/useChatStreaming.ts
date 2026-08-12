import type { MessageUiStatus, ResponseStatus, StreamingDeps, UnifiedToolResponse } from '~/types/message';
import {
  isLocalChartTaskId,
  normalizeUnifiedToolResponse,
  unifiedResponseToMarkerText,
} from '~/utils/tool';
import {
  isChatApiConfigured,
  handleNormalizedChatResponse,
  legacyChatResponseToMessageParts,
  ChatStreamEventError,
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
    let normalizedDone: Record<string, unknown> | null = null;
    let firstDelta = true;
    const attachments = await prepareAttachments(files);

    try {
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
          deps.upsertAssistantMessage(assistantMsgId, '', {
            status: 'streaming',
            responseStatus: 'processing',
            blocks: [],
            requestId: typeof data.request_id === 'string' ? data.request_id : undefined,
            chatId: typeof data.chat_id === 'string' ? data.chat_id : undefined,
            streamingContent: '',
            error: null,
          });
        },
        onDelta: (content) => {
          if (deps.stopStreaming.value) return;
          if (firstDelta) {
            firstDelta = false;
            deps.currentRenderType.value = 'markdown';
          }
          const existing = deps.getAssistantMessage(assistantMsgId);
          const baseContent = existing?.content ?? currentContent;
          currentContent = `${baseContent}${content}`;
          deps.upsertAssistantMessage(assistantMsgId, currentContent, {
            status: 'streaming',
            blocks: streamingMarkdownBlock(assistantMsgId, currentContent),
            streamingContent: currentContent,
          });
        },
        onDone: (data) => {
          normalizedDone = data;
        },
        onError: (data) => {
          const detail = String(data.detail ?? 'Chat stream failed');
          const existing = deps.getAssistantMessage(assistantMsgId);
          const preservedContent = existing?.content || currentContent;
          const nextContent = preservedContent || detail;
          deps.upsertAssistantMessage(assistantMsgId, nextContent, {
            status: 'error',
            responseStatus: 'failed',
            blocks: preservedContent
              ? streamingMarkdownBlock(assistantMsgId, preservedContent)
              : streamErrorBlock(assistantMsgId, detail),
            streamingContent: preservedContent,
            error: detail,
          });
        },
      });
    } catch (error) {
      if (error instanceof ChatStreamEventError) return;
      throw error;
    }

    if (deps.stopStreaming.value || controller.signal.aborted) return;
    const normalizedParts = handleNormalizedChatResponse(normalizedDone, assistantMsgId);
    if (normalizedParts) {
      deps.upsertAssistantMessage(assistantMsgId, normalizedParts.content, {
        blocks: normalizedParts.blocks,
        sources: normalizedParts.sources,
        generationDurationMs: normalizedParts.latencyMs ?? Date.now() - startedAt,
        status: responseStatusToUiStatus(normalizedParts.status),
        responseStatus: normalizedParts.status,
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
        blocks: legacyParts.blocks,
        sources: legacyParts.sources,
        generationDurationMs: Date.now() - startedAt,
        status: responseStatusToUiStatus(legacyParts.status),
        responseStatus: legacyParts.status,
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
    deps.upsertAssistantMessage(assistantMsgId, markerText || currentContent, {
      generationDurationMs: Date.now() - startedAt,
      status: 'completed',
    });
    notifyResponseCompleted();
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
