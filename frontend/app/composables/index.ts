import { ref } from 'vue';
import type { Message } from '~/types/message';
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
import { ChatApiRequestError } from '~/services/chat-api';

export { useChatList } from './chat/useChatList';
export { useRenderer } from './renderers/useRenderer';

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

  const { streamFromChatApi } = useChatStreaming({
    chatId,
    chatApi: chatApiConfig,
    stopStreaming,
    streamController,
    currentRenderType,
    typing,
    upsertAssistantMessage,
    getAssistantMessage,
    getUiBlockDelay,
  });

  async function send(text: string, files?: unknown[]) {
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

      await streamFromChatApi(text, files, assistantMsgId, conversationMessages);
      return false;
    } catch (error) {
      failed = true;
      const normalizedErrorMessage = (() => {
        if (error instanceof ChatApiRequestError) {
          const body = error.body?.trim();
          const detail = body ? `\n\nDetails: ${body}` : '';
          return `Chat API request failed (${error.status}). Please verify your model is loaded and server is running.${detail}`;
        }
        if (error instanceof Error && error.message?.trim()) {
          return error.message.trim();
        }
        return 'I apologize, but something went wrong. Please try again.';
      })();

      const latestAssistant = messages.value.slice().reverse().find((m) => m.role === 'assistant');
      if (latestAssistant) {
        latestAssistant.status = 'failed';
        latestAssistant.content = latestAssistant.content?.trim()
          ? latestAssistant.content
          : normalizedErrorMessage;
      } else {
        messages.value.push({
          id: uid('msg'),
          role: 'assistant',
          status: 'failed',
          content: normalizedErrorMessage,
          createdAt: new Date().toISOString(),
        });
      }
      return false;
    } finally {
      if (assistantMsgId && !failed && !stopStreaming.value) {
        const assistant = messages.value.find((message) => message.id === assistantMsgId);
        if (assistant?.role === 'assistant') assistant.status = 'completed';
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
      latestAssistant.status = latestAssistant.content?.trim() ? 'completed' : 'failed';
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

    const text = JSON.stringify({
      message: '',
      meta: { continuation: payload },
    });
    await send(text);
  }

  return { messages, input, loading, currentRenderType, send, sendUserReply, stop, regenerate };
}
