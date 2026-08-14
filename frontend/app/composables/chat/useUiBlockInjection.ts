import type {
  AnswerConfidence,
  AnswerCoverage,
  MessageBlock,
  MessageSource,
  MessageUiStatus,
  ResponseStatus,
  UiBlockInjectionOptions,
} from '~/types/message';
import {
  isUnreliableServiceFallbackText,
  normalizeAssistantContentForUi,
  UNRELIABLE_SERVICE_FALLBACK_MESSAGE,
} from '~/utils/chat';
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
      status?: MessageUiStatus;
      responseStatus?: ResponseStatus;
      blocks?: MessageBlock[];
      sources?: MessageSource[];
      coverage?: AnswerCoverage;
      confidence?: AnswerConfidence;
      requestId?: string;
      chatId?: string;
      responseMode?: 'sync' | 'async' | 'stream';
      progressStage?: string;
      progressMessage?: string;
      streamingContent?: string;
      normalizedResponse?: unknown;
      error?: string | null;
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
    const nextBlocks = protectUnreliableFallbackBlocks(
      meta?.blocks ?? parseAiResponse(displayContent),
    );
    const hasUnreliableFallback = nextBlocks.some(isUnreliableFallbackErrorBlock);
    const syncedContent = hasUnreliableFallback
      ? blocksToMarkerText(nextBlocks)
      : displayContent || (nextBlocks.length ? blocksToMarkerText(nextBlocks) : '');

    messages[index] = {
      id: existingMessage.id,
      role: existingMessage.role,
      status: hasUnreliableFallback ? 'error' : meta?.status ?? existingMessage.status,
      responseStatus: hasUnreliableFallback ? 'failed' : meta?.responseStatus ?? existingMessage.responseStatus,
      content: syncedContent,
      type: existingMessage.type,
      imageContent: existingMessage.imageContent,
      files: existingMessage.files,
      createdAt: existingMessage.createdAt,
      blocks: nextBlocks,
      sources: meta?.sources ?? existingMessage.sources,
      generationDurationMs: meta?.generationDurationMs ?? existingMessage.generationDurationMs,
      requestId: meta?.requestId ?? existingMessage.requestId,
      chatId: meta?.chatId ?? existingMessage.chatId,
      responseMode: meta?.responseMode ?? existingMessage.responseMode,
      progressStage: meta?.progressStage ?? existingMessage.progressStage,
      progressMessage: meta?.progressMessage ?? existingMessage.progressMessage,
      streamingContent: meta?.streamingContent ?? existingMessage.streamingContent,
      normalizedResponse: meta?.normalizedResponse ?? existingMessage.normalizedResponse,
      error: meta?.error === undefined ? existingMessage.error : meta.error ?? undefined,
      coverage: meta?.coverage ?? existingMessage.coverage,
      confidence: meta?.confidence ?? existingMessage.confidence,
    };
  }

  return {
    getAssistantMessage,
    upsertAssistantMessage,
  };
}

function protectUnreliableFallbackBlocks(blocks: MessageBlock[]): MessageBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'markdown' || typeof block.content !== 'string') {
      return block;
    }
    if (isUnreliableServiceFallbackText(block.content)) {
      return unreliableServiceFallbackErrorBlock(`${block.id}-unreliable-fallback`);
    }
    return {
      ...block,
      content: normalizeAssistantContentForUi(block.content),
    };
  });
}

function unreliableServiceFallbackErrorBlock(id: string): MessageBlock {
  return {
    id,
    type: 'error',
    content: {
      title: 'Response unavailable',
      message: UNRELIABLE_SERVICE_FALLBACK_MESSAGE,
    },
    isComplete: true,
  };
}

function isUnreliableFallbackErrorBlock(block: MessageBlock): boolean {
  return block.type === 'error' &&
    typeof block.content === 'object' &&
    block.content !== null &&
    'message' in block.content &&
    block.content.message === UNRELIABLE_SERVICE_FALLBACK_MESSAGE;
}
