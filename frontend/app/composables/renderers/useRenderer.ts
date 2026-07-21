import type { Component } from 'vue';
import {
  canonicalizeBlockType,
  envelopeToMarkerText,
  normalizeRawAiResponse,
  parseAiResponse,
  parseAiResponseWithAsyncTasks,
  serializeMessageBlock,
} from '~/utils/message';
import { isUnifiedToolResponse, normalizeUnifiedToolResponse } from '~/utils/tool';
import type { MessageBlock, UnifiedAsyncTaskState, UnifiedToolResponse } from '~/types/message';
import MarkdownRenderer from '~/components/renderers/MarkdownRenderer.vue';
import TypingIndicator from '~/components/common/TypingIndicator.vue';
import TableRenderer from '~/components/renderers/TableRenderer.vue';
import ChartTaskRenderer from '~/components/renderers/ChartTaskRenderer.vue';
import WorkflowRenderer from '~/components/renderers/WorkflowRenderer.vue';
import ImageRenderer from '~/components/renderers/ImageRenderer.vue';
import PredictionRenderer from '~/components/renderers/PredictionRenderer.vue';
import ReportTaskRenderer from '~/components/renderers/ReportTaskRenderer.vue';
import SuggestionsRenderer from '~/components/renderers/SuggestionsRenderer.vue';
import CoverageRenderer from '~/components/renderers/CoverageRenderer.vue';
import CodeBlockRenderer from '~/components/renderers/CodeBlockRenderer.vue';
import ToolOutputRenderer from '~/components/renderers/ToolOutputRenderer.vue';
import ErrorRenderer from '~/components/renderers/ErrorRenderer.vue';
import OCRRenderer from '~/components/renderers/OCRRenderer.vue';
import InteractionRenderer from '~/components/renderers/InteractionRenderer.vue';

const DEFAULT_TYPING_LABEL = 'Thinking...';

export const rendererMap: Record<string, Component> = {
  markdown: MarkdownRenderer,
  reasoning: TypingIndicator,
  table: TableRenderer,
  chart: ChartTaskRenderer,
  workflow: WorkflowRenderer,
  image: ImageRenderer,
  prediction: PredictionRenderer,
  report: ReportTaskRenderer,
  suggestions: SuggestionsRenderer,
  coverage: CoverageRenderer,
  code: CodeBlockRenderer,
  ocr: OCRRenderer,
  interaction: InteractionRenderer,
  tool_output: ToolOutputRenderer,
  error: ErrorRenderer,
  fallback: MarkdownRenderer,
};

// ─── Block Type Descriptions ─────────────────────────────────────────────────
// Human-readable labels for each canonical block type.
export const blockTypeLabels: Record<string, string> = {
  markdown: 'Markdown', reasoning: 'Reasoning', table: 'Table', chart: 'Chart',
  workflow: 'Workflow', image: 'Image', prediction: 'Prediction', report: 'Report',
  suggestions: 'Suggestions', coverage: 'Coverage', code: 'Code', ocr: 'OCR', interaction: 'Interaction', tool_output: 'Tool Output',
  error: 'Error', fallback: 'Fallback',
};

const streamingVisibleTypes = new Set(['markdown', 'reasoning', 'chart', 'workflow']);

// ─── Coverage Invariant ──────────────────────────────────────────────────────
// Both the renderer map and labels MUST stay aligned. We assert key coverage at
// module load to catch drift early in dev.
export { useTableRenderer } from './useTableRenderer';
export { useChartRenderer } from './useChartRenderer';
export { useWorkflowRenderer } from './useWorkflowRenderer';
export { useImageRenderer } from './useImageRenderer';
export { useOCRRenderer } from './useOCRRenderer';
export { usePredictionRenderer } from './usePredictionRenderer';
export { useCodeBlockRenderer } from './useCodeRenderer';
export { useErrorRenderer, useFriendlyErrorDisplay } from './useErrorRenderer';
export type { ErrorDisplayKind } from './useErrorRenderer';
export { useReportRenderer } from './useReportRenderer';

// ─── Type Re-exports ─────────────────────────────────────────────────────────
export type {
  BulletLegendItem,
  ChartKind,
  ChartOutput,
  ChartSeries,
  ChartUIToolInvocation,
  OCRData,
  Prediction,
  TableColumn,
  TableData,
  WorkflowData,
  WorkflowStep,
} from '~/types/message';

export function useRenderer() {
  function parseBlocks(input: string | UnifiedToolResponse | null | undefined): MessageBlock[] {
    if (!input) return [];
    if (typeof input === 'string') return normalizeRawAiResponse(input);
    return parseAiResponse(input);
  }

  function normalizeUnified(envelope: UnifiedToolResponse): {
    blocks: MessageBlock[];
    asyncTasks: UnifiedAsyncTaskState[];
  } {
    const result = normalizeUnifiedToolResponse(envelope);
    return { blocks: result.blocks, asyncTasks: result.asyncTasks };
  }

  function serializeBlock(type: string, content: unknown): string {
    return serializeMessageBlock(type, content);
  }

  function serializeUnified(envelope: UnifiedToolResponse): string {
    return envelopeToMarkerText(envelope);
  }

  function resolveRenderer(type: string): Component {
    const canonical = canonicalizeBlockType(type);
    return rendererMap[canonical] ?? rendererMap.fallback ?? rendererMap.markdown;
  }

  function isKnownType(type: string): boolean {
    const canonical = canonicalizeBlockType(type);
    return canonical in rendererMap;
  }

  function getLabel(type: string): string {
    const canonical = canonicalizeBlockType(type);
    return blockTypeLabels[canonical] ?? type;
  }

  function getTypingLabel(_type: string): string {
    return DEFAULT_TYPING_LABEL;
  }

  function isStreamingVisible(_type: string): boolean {
    const canonical = canonicalizeBlockType(_type);
    return streamingVisibleTypes.has(canonical);
  }

  return {
    rendererMap,
    blockTypeLabels,
    parseBlocks,
    parseAiResponseWithAsyncTasks,
    serializeBlock,
    serializeUnified,
    normalizeUnified,
    isUnifiedEnvelope: isUnifiedToolResponse,
    resolveRenderer,
    isKnownType,
    getLabel,
    getTypingLabel,
    isStreamingVisible,
  };
}
