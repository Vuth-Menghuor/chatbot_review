import type { Component, ComputedRef, Ref } from 'vue';

import type { ChatApiStreamingConfig } from './chatApi';

// ─── Core Message Roles ───────────────────────────────────────────────────
export type MessageRole = 'user' | 'assistant' | 'system';
export type ResponseStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'clarification_required'
  | 'partial'
  | 'failed';

export type MessageUiStatus = 'thinking' | 'streaming' | 'completed' | 'error' | 'stopped';

export type ResponseMode = 'sync' | 'async' | 'stream';

// ─── Block Types ────────────────────────────────────────────────────────────
// Canonical render types map 1:1 with renderer components in `app/composables/renderers/useRenderer.ts`.
// All inbound aliases are normalized to a canonical type via `canonicalizeBlockType`.
export type CanonicalMessageBlockType =
  | 'markdown'
  | 'reasoning'
  | 'summary'
  | 'key_value'
  | 'code'
  | 'table'
  | 'details'
  | 'references'
  | 'official_reference'
  | 'clarification'
  | 'image'
  | 'chart'
  | 'workflow'
  | 'ocr'
  | 'prediction'
  | 'report'
  | 'suggestions'
  | 'coverage'
  | 'interaction'
  | 'tool_output'
  | 'error'
  | 'fallback';

/**
 * Compatibility aliases accepted at API/parser boundaries. Always normalized
 * before reaching renderer lookup. Keep this list in sync with
 * `BLOCK_TYPE_ALIASES` in `app/utils/canonicalBlocks.ts`.
 */
export type AliasMessageBlockType =
  | 'text'
  | 'json'
  | 'file'
  | 'mcp'
  | 'tool'
  | 'tool_result'
  | 'chart_task'
  | 'report_task'
  | 'steps'
  | 'structured';

export type MessageBlockType = CanonicalMessageBlockType | AliasMessageBlockType;

// ─── Composable Contracts ───────────────────────────────────────────────────
// ─── Action Interface ───────────────────────────────────────────────────────
export interface MessageSource {
  title: string;
  url?: string;
  snippet?: string;
  domain?: string;
  favicon?: string;
  id?: string;
  citationId?: string;
  documentId?: string;
  filename?: string;
  chunkIndex?: number;
  retrievalMethod?: string;
}

export type AnswerCoverage = 'complete' | 'partial' | 'unknown';
export type AnswerConfidence = 'high' | 'medium' | 'low';

export type ChatActionType = 'copy' | 'like' | 'dislike' | 'regenerate' | 'edit' | 'sources';
export type FeedbackType = 'like' | 'dislike';

export interface ChatActionItem {
  icon: Component;
  tooltip: string;
  action: ChatActionType;
}

export interface UseChatActionEmit {
  (e: 'copy', content: string): void;
  (e: 'like', messageId: string | number): void;
  (e: 'dislike', messageId: string | number): void;
  (e: 'regenerate', messageId: string | number): void;
  (e: 'edit', messageId: string | number): void;
}

export interface UseChatMessageRenderFlowProps {
  message: Message;
  loading?: boolean;
  currentRenderType?: string;
  thinkingContext?: string;
}

export interface TypingConfig {
  baseDelayMs: number;
  randomJitterMs: number;
  flushIntervalMs: number;
  sentencePauseMs: number;
  clausePauseMs: number;
  wordPauseMs: number;
}

/**
 * Block type names accepted from the prompt/mock pipeline.
 * Canonical names are preferred; aliases are kept for backward compatibility
 * and normalized at the renderer boundary.
 */
export type PromptBlockType = CanonicalMessageBlockType | 'chart_task' | 'report_task' | 'steps';

export interface PromptBlock {
  type: PromptBlockType;
  content: unknown;
}

export interface PromptPayload {
  version: 'v1';
  route: string;
  markdown: string;
  blocks: PromptBlock[];
}

export interface StreamingDeps {
  chatId?: string;
  projectId?: string;
  /** When set, the chat send pipeline routes through Chat API. */
  chatApi?: ChatApiStreamingConfig;
  stopStreaming: { value: boolean };
  streamController: { value: AbortController | null };
  currentRenderType: { value: string };
  typing: {
    config: TypingConfig;
    sleep: (ms: number) => Promise<void>;
    applyNaturalPause: (text: string) => Promise<void>;
    getPiecePause: (piece: string) => number;
  };
  upsertAssistantMessage: (
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
      responseMode?: ResponseMode;
      progressStage?: string;
      progressMessage?: string;
      streamingContent?: string;
      normalizedResponse?: unknown;
      error?: string | null;
    },
  ) => void;
  getAssistantMessage: (messageId: string) => Message | null;
  getUiBlockDelay: (type: string) => number;
}

export interface UiBlockInjectionOptions {
  messages: Ref<Message[]>;
}

// ─── Action Interface ───────────────────────────────────────────────────────
export interface MessageAction {
  key: string;
  label: string;
}

// ─── Message Block ──────────────────────────────────────────────────────────
export interface MessageBlock {
  id: string;
  type: MessageBlockType;
  title?: string;
  status?: 'pending' | 'processing' | 'completed' | 'failed';
  content: unknown;
  meta?: Record<string, unknown>;
  isComplete?: boolean;
  actions?: MessageAction[];
}

// ─── Typewriter (UI) ────────────────────────────────────────────────────────
export interface UseTypewriterOptions {
  config?: Partial<TypingConfig>;
  maxCharsPerTick?: number;
}

export interface UseTypewriterResult {
  typedText: ComputedRef<string>;
  isTyping: ComputedRef<boolean>;
  done: ComputedRef<boolean>;
  flush: () => void;
  reset: () => void;
}

// ─── Stores / projects ───────────────────────────────────────────────────────
export interface Chat {
  id: string;
  backendId?: string;
  title: string;
  projectId?: string;
  backendProjectId?: string;
  createdAt: string;
  lastMessage?: string;
  pinned?: boolean;
}

export interface Project {
  id: string;
  backendId?: string;
  name: string;
  description?: string;
  createdAt: string;
}

export interface ProjectCategory {
  id: string;
  name: string;
  emoji: string;
}

// ─── Legacy Compat Interfaces ──────────────────────────────────────────────
export interface ImageContent {
  prompt: string;
  imageUrl?: string;
  loading?: boolean;
  error?: boolean;
}

export interface Message {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  type?: 'text' | 'image';
  status?: MessageUiStatus;
  responseStatus?: ResponseStatus;
  feedback?: 'like' | 'dislike' | null;
  content: string;
  imageContent?: ImageContent;
  files?: unknown[];
  createdAt?: string;
  blocks?: MessageBlock[];
  sources?: MessageSource[];
  generationDurationMs?: number;
  requestId?: string;
  chatId?: string;
  responseMode?: ResponseMode;
  progressStage?: string;
  progressMessage?: string;
  streamingContent?: string;
  normalizedResponse?: unknown;
  error?: string;
  coverage?: AnswerCoverage;
  confidence?: AnswerConfidence;
}
