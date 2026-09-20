import { computed, ref } from 'vue';
import type { Message, MessageBlock } from '~/types/message';
import { useAuthStore } from '~/stores/auth.store';
import { useChatStore } from '~/stores/chat.store';
import { uid } from '~/utils/id';
import { useRenderAnimation } from './common/useRenderAnimation';
import { useChatTitle } from './chat/useChatTitle';
import { useChatPersistence } from './chat/useChatPersistence';
import { useChatTypingSimulation } from './chat/useChatTypingSimulation';
import { useUiBlockInjection } from './chat/useUiBlockInjection';
import { useChatStreaming } from './chat/useChatStreaming';
import { canonicalizeBlockType } from '~/utils/message';
import { ChatApiRequestError, getChatHistoryRequest } from '~/services/chat-api';
import { backendUuidOrNull } from '~/utils/id/backendIdentity';

export { useChatList } from './chat/useChatList';

export function useChat(chatId?: string) {
  const chatStore = useChatStore();
  const authStore = useAuthStore();
  const runtimeConfig = useRuntimeConfig();
  const normalizeBaseUrl = (value: string) => value.replace(/\/+$/, '');

  const gdceApiEnabled = Boolean(runtimeConfig.public?.gdceApiEnabled ?? true);
  const chatApiBaseUrl = normalizeBaseUrl(String(runtimeConfig.public?.gdceApiBaseUrl ?? 'http://localhost:8000'));
  const chatApiConfig = gdceApiEnabled
    ? {
        baseUrl: chatApiBaseUrl,
        apiToken: authStore.accessToken ?? '',
        model: 'gdce-orchestrator',
        contextLength: 8000,
        temperature: 0,
        transport: 'gdce' as const,
      }
    : undefined;

  const { generateChatTitle } = useChatTitle();
  const { initialMessages, persistMessages } = useChatPersistence(chatId);
  const messages = ref<Message[]>(initialMessages);
  const input = ref('');
  const loading = ref(false);
  const stopStreaming = ref(false);
  const streamController = ref<AbortController | null>(null);
  const currentRenderType = ref<string>('thinking');
  const anim = useRenderAnimation();
  const typing = useChatTypingSimulation();
  const uiBlockDelayMsByType: Record<string, number> = {
    markdown: anim.blockEnterMs,
    reasoning: anim.thinkingMs,
    table: anim.tableRowMs * 3 + 60,
    chart: 650,
    workflow: anim.workflowStepMs * 3 + 80,
    image: 650,
    ocr: 650,
    prediction: 520,
    report: anim.reportStatusMs * 2,
    code: 320,
    tool_output: 320,
    error: 300,
    fallback: 300,
  };
  const getUiBlockDelay = (type: string) => {
    const canonical = canonicalizeBlockType(type);
    return uiBlockDelayMsByType[canonical] ?? anim.blockEnterMs;
  };

  persistMessages(messages);

  const { upsertAssistantMessage, getAssistantMessage } = useUiBlockInjection({ messages });
  const projectId = computed(() =>
    chatId ? chatStore.recentChats.find((chat) => chat.id === chatId)?.projectId : undefined,
  );

  const { streamFromChatApi } = useChatStreaming({
    chatId,
    get projectId() {
      return projectId.value;
    },
    chatApi: chatApiConfig,
    stopStreaming,
    streamController,
    currentRenderType,
    typing,
    upsertAssistantMessage,
    getAssistantMessage,
    getUiBlockDelay,
  });

  async function loadServerHistory(): Promise<boolean> {
    if (!chatId || !chatApiConfig?.baseUrl) return false;
    const chat = chatStore.recentChats.find((item) => item.id === chatId);
    const backendChatId = backendUuidOrNull(chat?.backendId);
    if (!backendChatId) return false;

    const token = await authStore.getValidAccessToken();
    if (!token) return false;

    try {
      const result = await getChatHistoryRequest(chatApiConfig.baseUrl, token, backendChatId);
      authStore.accessToken = result.accessToken;
      messages.value = result.data.messages.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        status: message.status === 'failed' ? 'error' : 'completed',
        responseStatus: message.status === 'failed' ? 'failed' : 'completed',
        createdAt: message.created_at,
      }));
      return true;
    } catch (error) {
      if (import.meta.dev) console.error('[GDCE chat history failed]', error);
      return false;
    }
  }

  function isAbortError(error: unknown) {
    return (
      stopStreaming.value ||
      streamController.value?.signal.aborted ||
      (error instanceof DOMException && error.name === 'AbortError') ||
      (error instanceof Error && error.name === 'AbortError')
    );
  }

  function friendlyChatError(error: unknown) {
    if (error instanceof ChatApiRequestError) {
      if (import.meta.dev) {
        console.error('[GDCE chat request failed]', {
          status: error.status,
          body: error.body,
          message: error.message,
        });
      }
      if (error.status === 400) {
        return 'Invalid chat request. Please check your message and try again.';
      }
      if (error.status === 401) {
        return 'Your session has expired. Please sign in again to continue.';
      }
      if (error.status === 403) {
        return 'You do not have access to this chat or project.';
      }
      if (error.status === 404) {
        return 'This chat or project does not exist anymore.';
      }
      if (error.status === 422) {
        return 'Invalid request data. Please refresh the page and try again.';
      }
      if (error.status === 503) {
        return 'The chat service is temporarily unavailable. Please try again in a moment.';
      }
      return 'The chat request could not be completed. Please try again.';
    }
    if (error instanceof Error && error.message.includes('Project workspace')) {
      return error.message;
    }
    if (error instanceof TypeError) {
      return 'We could not reach the chat service. Please check your connection and try again.';
    }
    return 'Something went wrong while generating the response. Please try again.';
  }

  function errorMessageBlock(messageId: string, message: string): MessageBlock {
    return {
      id: `${messageId}-stream-error`,
      type: 'error',
      content: {
        title: 'Response unavailable',
        message,
      },
      isComplete: true,
    };
  }

  async function send(text: string, files?: unknown[], context?: Record<string, unknown>) {
    if ((!text.trim() && (!files || files.length === 0)) || loading.value) return true;

    if (chatId && messages.value.filter((m) => m.role === 'user').length === 0) {
      chatStore.renameChat(chatId, generateChatTitle(text));
    }

    const userMsgId = uid('msg');
    messages.value.push({
      id: userMsgId,
      role: 'user',
      content: text,
      files: files || [],
      createdAt: new Date().toISOString(),
    });

    if (!chatApiConfig?.baseUrl) {
      messages.value.push({
        id: uid('msg'),
        role: 'assistant',
        status: 'completed',
        content: 'Chat API is not configured. Enable the GDCE API integration in .env, then restart the dev server.',
        createdAt: new Date().toISOString(),
      });
      return true;
    }

    loading.value = true;
    stopStreaming.value = false;
    currentRenderType.value = 'thinking';
    let assistantMsgId = '';
    let failed = false;

    const conversationMessages = messages.value
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => ({
        role: message.role as 'user' | 'assistant',
        content: message.content ?? '',
      }));

    try {
      assistantMsgId = uid('msg');
      messages.value.push({
        id: assistantMsgId,
        role: 'assistant',
        status: 'thinking',
        content: '',
        createdAt: new Date().toISOString(),
      });

      await streamFromChatApi(text, files, assistantMsgId, context);
      return false;
    } catch (error) {
      if (isAbortError(error)) {
        return false;
      }
      failed = true;
      const normalizedErrorMessage = friendlyChatError(error);

      if (assistantMsgId) {
        upsertAssistantMessage(assistantMsgId, normalizedErrorMessage, {
          status: 'error',
          responseStatus: 'failed',
          blocks: [errorMessageBlock(assistantMsgId, normalizedErrorMessage)],
          error: normalizedErrorMessage,
        });
      } else {
        messages.value.push({
          id: uid('msg'),
          role: 'assistant',
          status: 'error',
          responseStatus: 'failed',
          content: normalizedErrorMessage,
          blocks: [errorMessageBlock('chat-api-error', normalizedErrorMessage)],
          error: normalizedErrorMessage,
          createdAt: new Date().toISOString(),
        });
      }
      return false;
    } finally {
      if (assistantMsgId && !failed && !stopStreaming.value) {
        const assistant = messages.value.find((message) => message.id === assistantMsgId);
        if (
          assistant?.role === 'assistant' &&
          assistant.status !== 'error'
        ) {
          assistant.status = 'completed';
        }
      }
      streamController.value = null;
      currentRenderType.value = 'idle';
      loading.value = false;
    }
  }

  async function regenerate() {
    if (messages.value.length === 0 || loading.value) return;
    const lastUserMessage = [...messages.value].reverse().find((m) => m.role === 'user');
    if (lastUserMessage) {
      const lastMsg = messages.value[messages.value.length - 1];
      if (lastMsg && lastMsg.role === 'assistant') messages.value.pop();
      await send(lastUserMessage.content, lastUserMessage.files);
    }
  }

  function stop() {
    stopStreaming.value = true;
    streamController.value?.abort();
    streamController.value = null;
    const latestAssistant = messages.value.slice().reverse().find((message) => message.role === 'assistant');
    if (latestAssistant) {
      latestAssistant.status = 'stopped';
    }
    currentRenderType.value = 'idle';
    loading.value = false;
  }

  async function sendUserReply(payload: {
    requestId: string;
    toolName?: string;
    action: string;
    values: Record<string, unknown>;
  }) {
    if (payload.action === 'send_suggestion') {
      const message = String(payload.values.message ?? '').trim();
      if (message) await send(message);
      return;
    }

    const values = Object.values(payload.values)
      .map((value) => String(value ?? '').trim())
      .filter(Boolean);
    const displayMessage = values.length
      ? values.join('\n')
      : payload.action === 'cancel'
        ? 'Cancelled'
        : 'Submitted clarification';

    await send(displayMessage, undefined, {
      reply_to_request_id: payload.requestId,
      clarification_action: payload.action,
    });
  }

  return { messages, input, loading, currentRenderType, send, sendUserReply, stop, regenerate, loadServerHistory };
}
