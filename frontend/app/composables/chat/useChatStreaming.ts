import type { StreamingDeps, UnifiedToolResponse } from '~/types/message';
import {
  isLocalChartTaskId,
  normalizeUnifiedToolResponse,
  unifiedResponseToMarkerText,
} from '~/utils/tool';
import {
  isChatApiConfigured,
  isNormalizedChatResponse,
  legacyChatResponseToMessageParts,
  normalizedChatResponseToMessageParts,
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
    let firstToken = true;
    const attachments = await prepareAttachments(files);

    await streamGdceChat({
      baseUrl: deps.chatApi.baseUrl,
      apiToken: deps.chatApi.apiToken,
      message: text,
      chatId: deps.chatId,
      attachments,
      signal: controller.signal,
      onToken: (content) => {
        if (deps.stopStreaming.value) return;
        if (firstToken) {
          firstToken = false;
          deps.currentRenderType.value = 'markdown';
        }
        currentContent += content;
        deps.upsertAssistantMessage(assistantMsgId, currentContent, { status: 'streaming' });
      },
      onDone: (data) => {
        normalizedDone = data;
      },
    });

    if (deps.stopStreaming.value || controller.signal.aborted) return;
    if (isNormalizedChatResponse(normalizedDone)) {
      const parts = normalizedChatResponseToMessageParts(normalizedDone, assistantMsgId);
      deps.upsertAssistantMessage(assistantMsgId, parts.content, {
        blocks: parts.blocks,
        sources: parts.sources,
        generationDurationMs: parts.latencyMs ?? Date.now() - startedAt,
        status: parts.status,
        coverage: parts.coverage,
        confidence: parts.confidence,
      });
      notifyResponseCompleted();
      return;
    }
    const legacyParts = legacyChatResponseToMessageParts(normalizedDone, assistantMsgId);
    if (legacyParts) {
      deps.upsertAssistantMessage(assistantMsgId, legacyParts.content || currentContent, {
        blocks: legacyParts.blocks,
        sources: legacyParts.sources,
        generationDurationMs: Date.now() - startedAt,
        status: legacyParts.status,
        coverage: legacyParts.coverage,
        confidence: legacyParts.confidence,
      });
      notifyResponseCompleted();
      return;
    }

    const unified = {
      requestId: assistantMsgId,
      mode: 'stream',
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
