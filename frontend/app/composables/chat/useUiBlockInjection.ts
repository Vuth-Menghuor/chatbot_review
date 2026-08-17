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
      normalizedResponseContext(meta?.normalizedResponse),
    );
    const hasUnreliableFallback = nextBlocks.some(isUnreliableFallbackErrorBlock);
    const hasUsefulBlocks = nextBlocks.some(isUsefulAuthoritativeBlock);
    const shouldSuppressDisplayContent = hasUsefulBlocks &&
      isUnreliableServiceFallbackText(displayContent, normalizedResponseContext(meta?.normalizedResponse));
    const syncedContent = hasUnreliableFallback
      ? blocksToMarkerText(nextBlocks)
      : shouldSuppressDisplayContent
        ? blocksToMarkerText(nextBlocks)
        : displayContent || (nextBlocks.length ? blocksToMarkerText(nextBlocks) : '');
    const wouldEraseCompletedAssistant = meta?.status === 'completed' &&
      !syncedContent.trim() &&
      nextBlocks.length === 0 &&
      existingMessage.role === 'assistant' &&
      Boolean(
        existingMessage.content?.trim() ||
        existingMessage.streamingContent?.trim() ||
        existingMessage.blocks?.length,
      );
    if (wouldEraseCompletedAssistant) {
      if (import.meta.dev) {
        console.error('[upsertAssistantMessage] refusing empty completed assistant message', {
          messageId,
          incomingContent: content,
          displayContent,
          nextBlocks,
          previous: existingMessage,
          meta,
        });
      }
      messages[index] = {
        ...existingMessage,
        status: meta?.status ?? existingMessage.status,
        responseStatus: meta?.responseStatus ?? existingMessage.responseStatus,
        generationDurationMs: meta?.generationDurationMs ?? existingMessage.generationDurationMs,
        responseMode: meta?.responseMode ?? existingMessage.responseMode,
        progressStage: meta?.progressStage ?? existingMessage.progressStage,
        progressMessage: meta?.progressMessage ?? existingMessage.progressMessage,
        streamingContent: '',
        normalizedResponse: meta?.normalizedResponse ?? existingMessage.normalizedResponse,
        error: meta?.error === undefined ? existingMessage.error : meta.error ?? undefined,
        coverage: meta?.coverage ?? existingMessage.coverage,
        confidence: meta?.confidence ?? existingMessage.confidence,
      };
      return;
    }

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

function normalizedResponseContext(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const record = value as Record<string, unknown>;
  return {
    service: record.service,
    intent: record.intent,
  };
}

function protectUnreliableFallbackBlocks(
  blocks: MessageBlock[],
  context: { service?: unknown; intent?: unknown } = {},
): MessageBlock[] {
  const normalizedBlocks = blocks.map((block) => {
    if (block.type !== 'markdown' || typeof block.content !== 'string') {
      return block;
    }
    if (isUnreliableServiceFallbackText(block.content, context)) {
      return unreliableServiceFallbackErrorBlock(`${block.id}-unreliable-fallback`);
    }
    return {
      ...block,
      content: normalizeAssistantContentForUi(block.content),
    };
  });

  const usefulBlocks = normalizedBlocks.filter(isUsefulAuthoritativeBlock);
  if (usefulBlocks.length) {
    return normalizedBlocks.filter((block) => !isUnreliableFallbackErrorBlock(block) && !isEmptyTableBlock(block));
  }

  return normalizedBlocks.filter((block) => !isEmptyTableBlock(block));
}

function isUsefulAuthoritativeBlock(block: MessageBlock): boolean {
  if (isUnreliableFallbackErrorBlock(block)) return false;
  if (block.type === 'table') return hasPopulatedTableRows(block);
  if (block.type === 'markdown') return typeof block.content === 'string' && block.content.trim().length > 0;
  if (block.type === 'error' || block.type === 'fallback') return false;
  return true;
}

function hasPopulatedTableRows(block: MessageBlock): boolean {
  const content = block.content;
  if (!content || typeof content !== 'object' || Array.isArray(content)) return false;
  const rows = (content as Record<string, unknown>).rows;
  return Array.isArray(rows) && rows.length > 0;
}

function isEmptyTableBlock(block: MessageBlock): boolean {
  return block.type === 'table' && !hasPopulatedTableRows(block);
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
