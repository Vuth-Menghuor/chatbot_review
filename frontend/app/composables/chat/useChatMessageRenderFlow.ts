import { computed, watch } from 'vue';
import type {
  MessageBlock,
  MessageBlockType,
  UseChatMessageRenderFlowProps,
} from '~/types/message';
import { isMessageBlockJsonCode } from '../renderers/useCodeRenderer';
import { useRenderer } from '../renderers/useRenderer';
import { useRenderAnimation } from '../common/useRenderAnimation';

export function useChatMessageRenderFlow(props: UseChatMessageRenderFlowProps) {
  const { parseBlocks, resolveRenderer, getTypingLabel, isStreamingVisible } = useRenderer();
  const anim = useRenderAnimation();

  function buildThinkingText(input?: string) {
    const normalized = (input ?? '').replace(/\s+/g, ' ').trim();
    if (!normalized) return 'Understanding the request...';
    const withoutQuestionMark = normalized.replace(/[?.!]+$/, '');
    const preview =
      withoutQuestionMark.length > 78
        ? `${withoutQuestionMark.slice(0, 78).trim()}...`
        : withoutQuestionMark;
    return `The user is asking about ${preview}...`;
  }

  const imageBlock = computed(() => {
    const ic = props.message.imageContent;
    if (!ic) return null;

    return {
      id: props.message.id ?? 'img-block',
      type: 'image' as MessageBlockType,
      content: {
        imageUrl: ic.imageUrl,
        prompt: ic.prompt,
        loading: ic.loading,
        error: ic.error,
      },
    };
  });

  const blocks = computed(() => {
    if (props.message.type === 'image') return [];
    if (props.message.blocks?.length) return props.message.blocks;
    if (typeof props.message.content !== 'string') return [];
    return parseBlocks(props.message.content);
  });

  watch(
    blocks,
    (nextBlocks) => {
      const predBlock = nextBlocks.find((b) => b.type === 'prediction');
      if (predBlock && predBlock.content && typeof predBlock.content === 'object') {
        const data = predBlock.content as Record<string, unknown>;
        if (data.sourceUrl) {
          if (!props.message.sources) {
            props.message.sources = [];
          }
          const sourceUrl = String(data.sourceUrl);
          const exists = props.message.sources.some((s) => s.url === sourceUrl);
          if (!exists) {
            props.message.sources.push({
              title: typeof data.sourceName === 'string' ? data.sourceName : 'Source',
              url: sourceUrl,
              domain: (() => {
                try {
                  return new URL(sourceUrl).hostname.replace(/^www\./, '');
                } catch {
                  return '';
                }
              })(),
            });
          }
        }
      }
    },
    { immediate: true },
  );

  const hasParsedBlocks = computed(() => blocks.value.length > 0);
  const messageStatus = computed(() => props.message.status?.toLowerCase() ?? 'idle');
  const shouldShowWaitingIndicator = computed(
    () => messageStatus.value === 'thinking' || messageStatus.value === 'loading',
  );
  const realReasoningBlock = computed(
    () => blocks.value.find((block) => block.type === 'reasoning') ?? null,
  );
  const syntheticReasoningBlock = computed<MessageBlock | null>(() => {
    if (
      !shouldShowWaitingIndicator.value ||
      realReasoningBlock.value ||
      hasNonReasoningBlocks.value
    ) {
      return null;
    }
    return {
      id: `${props.message.id ?? 'assistant'}-thinking`,
      type: 'reasoning',
      content: {
        text: buildThinkingText(props.thinkingContext),
        streaming: true,
      },
      isComplete: false,
    };
  });
  const nonReasoningBlocks = computed(() =>
    blocks.value.filter((block) => block.type !== 'reasoning'),
  );
  const hasNonReasoningBlocks = computed(() => nonReasoningBlocks.value.length > 0);
  const currentType = computed(() => props.currentRenderType?.toLowerCase() ?? 'thinking');
  const isStillReasoning = computed(
    () => currentType.value === 'thinking' || currentType.value === 'reasoning',
  );

  /** While markdown is streaming, always show the body even if `currentRenderType` lags on `thinking`. */
  const hasStreamingAssistantMarkdown = computed(() =>
    Boolean(
      props.loading &&
      hasNonReasoningBlocks.value &&
      nonReasoningBlocks.value.some((b) => b.type === 'markdown'),
    ),
  );

  /** Same as markdown: show code fences (via MarkdownRenderer) while streaming even during a reasoning turn. */
  const hasStreamingAssistantCode = computed(() =>
    Boolean(
      props.loading &&
      hasNonReasoningBlocks.value &&
      nonReasoningBlocks.value.some(
        (b) => b.type === 'code' || b.type === 'ocr' || b.type === 'tool_output',
      ),
    ),
  );

  /** Tables, charts, workflows, etc. from `gdce-render` / API — show as soon as parsed, not only after stream ends. */
  const hasStreamingStructuredBlocks = computed(() =>
    Boolean(
      props.loading &&
      hasNonReasoningBlocks.value &&
      nonReasoningBlocks.value.some((b) => isStreamingVisible(b.type)),
    ),
  );

  const hasStreamingRichContent = computed(
    () =>
      hasStreamingAssistantMarkdown.value ||
      hasStreamingAssistantCode.value ||
      hasStreamingStructuredBlocks.value,
  );

  const reasoningBlock = computed(() => realReasoningBlock.value ?? syntheticReasoningBlock.value);

  const shouldShowTypingPhase = computed(() =>
    Boolean(shouldShowWaitingIndicator.value && !hasParsedBlocks.value && !reasoningBlock.value),
  );
  const shouldShowReasoningPhase = computed(
    () =>
      Boolean(reasoningBlock.value) &&
      (!shouldShowTypingPhase.value || Boolean(realReasoningBlock.value)),
  );
  const shouldShowRenderPhase = computed(() => {
    if (!hasNonReasoningBlocks.value) return !props.loading && !reasoningBlock.value;
    if (hasStreamingRichContent.value) return true;
    return !props.loading || !isStillReasoning.value;
  });
  const shouldStreamReasoning = computed(() =>
    Boolean(props.loading && shouldShowReasoningPhase.value && !shouldShowRenderPhase.value),
  );
  const typingPhaseText = computed(() =>
    props.currentRenderType && props.currentRenderType !== 'thinking'
      ? `Generating ${props.currentRenderType}...`
      : 'Thinking...',
  );

  const visibleReasoningBlock = computed(() => {
    if (!reasoningBlock.value || !shouldShowReasoningPhase.value) return null;
    if (shouldShowRenderPhase.value && !shouldStreamReasoning.value) return null;
    return reasoningBlock.value;
  });

  const visibleBlocks = computed(() => {
    if (!shouldShowRenderPhase.value) {
      return visibleReasoningBlock.value ? [visibleReasoningBlock.value] : [];
    }

    if (!visibleReasoningBlock.value) return nonReasoningBlocks.value;
    return [visibleReasoningBlock.value, ...nonReasoningBlocks.value];
  });

  const getTypingText = (block: MessageBlock) => {
    if (isMessageBlockJsonCode(block)) return 'Formatting data...';
    return getTypingLabel(block.type);
  };

  const getBlockAnimId = (block: MessageBlock) => {
    const content = block.content;
    if (!content || typeof content !== 'object' || Array.isArray(content)) return undefined;
    return (content as Record<string, unknown>).__animId as string | undefined;
  };

  const isLatestVisibleBlock = (index: number) => index === visibleBlocks.value.length - 1;
  const isBlockLoading = (block: MessageBlock, index: number) =>
    Boolean(props.loading && !block.isComplete && isLatestVisibleBlock(index));
  const BLOCKS_WITHOUT_TYPING_INDICATOR = new Set<MessageBlockType>([
    'markdown',
    'reasoning',
    'code',
    'ocr',
    'tool_output',
  ]);
  const shouldShowBlockTypingIndicator = (block: MessageBlock, index: number) =>
    Boolean(
      props.loading &&
      shouldShowWaitingIndicator.value &&
      isLatestVisibleBlock(index) &&
      !BLOCKS_WITHOUT_TYPING_INDICATOR.has(block.type) &&
      !block.isComplete,
    );

  return {
    anim,
    imageBlock,
    visibleBlocks,
    reasoningBlock,
    shouldShowTypingPhase,
    shouldShowReasoningPhase,
    shouldShowRenderPhase,
    shouldStreamReasoning,
    typingPhaseText,
    resolveRenderer,
    getTypingText,
    getBlockAnimId,
    isBlockLoading,
    shouldShowBlockTypingIndicator,
  };
}
