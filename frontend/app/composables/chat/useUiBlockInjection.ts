import type {
  AnswerConfidence,
  AnswerCoverage,
  MessageBlock,
  MessageSource,
  MessageStatus,
  UiBlockInjectionOptions,
} from '~/types/message';
import { normalizeAssistantContentForUi } from '~/utils/chat';
import { blocksToMarkerText, parseAiResponse } from '~/utils/message';

export function useUiBlockInjection({ messages }: UiBlockInjectionOptions) {
  const getMessages = () => messages.value;

  function getAssistantMessage(messageId: string) {
    return (
      getMessages().find((message) => message.id === messageId && message.role === 'assistant') ??
      null
    );
  }

  function upsertAssistantMessage(
    messageId: string,
    content: string,
    meta?: {
      generationDurationMs?: number;
      status?: MessageStatus;
      blocks?: MessageBlock[];
      sources?: MessageSource[];
      coverage?: AnswerCoverage;
      confidence?: AnswerConfidence;
    },
  ) {
    const messages = getMessages();
    const index = messages.findIndex((msg) => msg.id === messageId);

    if (index === -1) {
      return;
    }

    const existingMessage = messages[index];
    if (!existingMessage) {
      return;
    }

    const displayContent = normalizeAssistantContentForUi(content);
    const nextBlocks = meta?.blocks ?? parseAiResponse(displayContent);
    const syncedContent = displayContent || (nextBlocks.length ? blocksToMarkerText(nextBlocks) : '');

    messages[index] = {
      id: existingMessage.id,
      role: existingMessage.role,
      status: meta?.status ?? existingMessage.status,
      content: syncedContent,
      type: existingMessage.type,
      imageContent: existingMessage.imageContent,
      files: existingMessage.files,
      createdAt: existingMessage.createdAt,
      blocks: nextBlocks,
      sources: meta?.sources ?? existingMessage.sources,
      generationDurationMs: meta?.generationDurationMs ?? existingMessage.generationDurationMs,
      coverage: meta?.coverage ?? existingMessage.coverage,
      confidence: meta?.confidence ?? existingMessage.confidence,
    };
  }

  return {
    getAssistantMessage,
    upsertAssistantMessage,
  };
}
