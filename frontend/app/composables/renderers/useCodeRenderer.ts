import { computed, unref, type MaybeRef } from 'vue';
import {
  LucideBraces,
  LucideDatabase,
  LucideFileCode2,
  LucideFileJson2,
  LucideSigma,
} from 'lucide-vue-next';
import { canonicalizeBlockType } from '~/utils/message';
import { normalizeShikiLanguage } from '~/utils/code';
import type { MessageBlock } from '~/types/message';
import { useClipboardCopy } from '~/composables/common/useClipboardCopy';

interface CodeBlockContent {
  code?: unknown;
  content?: unknown;
  text?: unknown;
  language?: unknown;
  lang?: unknown;
  toolName?: unknown;
  type?: unknown;
  mode?: unknown;
  status?: unknown;
  data?: {
    text?: unknown;
    language?: unknown;
    lang?: unknown;
  };
}

const LANG_ALIASES: Record<string, string> = {
  js: 'javascript',
  ts: 'typescript',
  node: 'javascript',
  py: 'python',
  rb: 'ruby',
  sh: 'bash',
  terminal: 'bash',
  console: 'bash',
  zsh: 'bash',
  ps: 'powershell',
  ps1: 'powershell',
  pwsh: 'powershell',
  command: 'batch',
  cmd: 'batch',
  bat: 'batch',
  yml: 'yaml',
  md: 'markdown',
  rs: 'rust',
  golang: 'go',
  kt: 'kotlin',
  kts: 'kotlin',
  'c++': 'cpp',
  htm: 'html',
  docker: 'dockerfile',
  gql: 'graphql',
  plist: 'xml',
  conf: 'toml',
  cs: 'csharp',
  'c#': 'csharp',
  text: 'markdown',
  txt: 'markdown',
  plain: 'markdown',
  plaintext: 'markdown',
};

const SUPPORTED_LANGS = new Set([
  'javascript',
  'typescript',
  'jsx',
  'tsx',
  'json',
  'bash',
  'shell',
  'powershell',
  'batch',
  'vue',
  'scss',
  'markdown',
  'yaml',
  'html',
  'css',
  'python',
  'sql',
  'go',
  'rust',
  'java',
  'c',
  'cpp',
  'csharp',
  'ruby',
  'php',
  'swift',
  'kotlin',
  'diff',
  'dockerfile',
  'xml',
  'toml',
  'graphql',
]);

export function isMessageBlockJsonCode(block: MessageBlock): boolean {
  const metaLang = block.meta?.language;
  if (typeof metaLang !== 'string' || metaLang.toLowerCase() !== 'json') {
    return false;
  }
  const canonical = canonicalizeBlockType(block.type);
  return canonical === 'code' || canonical === 'ocr' || canonical === 'tool_output';
}

export function useCodeBlockRenderer(block: MaybeRef<MessageBlock>) {
  const { copied, copyText } = useClipboardCopy({ resetMs: 1400 });

  const resolved = computed(() => unref(block));

  const structuredContent = computed<CodeBlockContent | undefined>(() => {
    const b = resolved.value;
    if (!b.content || typeof b.content !== 'object') return undefined;
    return b.content as CodeBlockContent;
  });

  const isJsonBlock = computed(() => {
    const b = resolved.value;
    const metaLang = b.meta?.language;
    return typeof metaLang === 'string' && metaLang.toLowerCase() === 'json';
  });

  const codeContent = computed(() => {
    const b = resolved.value;
    if (isJsonBlock.value) {
      // Incomplete: show raw tokens (string) or compact snapshot (object) — avoid parse/pretty until valid.
      if (!b.isComplete) {
        if (typeof b.content === 'string') return b.content;
        if (b.content && typeof b.content === 'object') {
          try {
            return JSON.stringify(b.content);
          } catch {
            return String(b.content);
          }
        }
        return String(b.content ?? '');
      }
      try {
        return typeof b.content === 'string'
          ? JSON.stringify(JSON.parse(b.content), null, 2)
          : JSON.stringify(b.content, null, 2);
      } catch {
        return String(b.content);
      }
    }
    if (structuredContent.value) {
      const ocrDataText = structuredContent.value.data?.text;
      const value =
        ocrDataText ??
        structuredContent.value.code ??
        structuredContent.value.content ??
        structuredContent.value.text ??
        structuredContent.value.data ??
        structuredContent.value;
      return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    }
    return String(b.content);
  });

  const language = computed(() => {
    if (isJsonBlock.value) return 'json';
    const b = resolved.value;
    const ocrDataLanguage =
      structuredContent.value?.data?.language ?? structuredContent.value?.data?.lang;
    const raw = (
      ocrDataLanguage ??
      structuredContent.value?.language ??
      structuredContent.value?.lang ??
      b.meta?.language ??
      'code'
    )
      .toString()
      .trim();
    if (!raw) return 'markdown';
    const rawLower = raw.toLowerCase();
    if (rawLower === 'code') return 'markdown';
    const normalized = LANG_ALIASES[rawLower] ?? rawLower;
    if (SUPPORTED_LANGS.has(normalized)) return normalized;
    return normalizeShikiLanguage(normalized);
  });

  const markdown = computed(() => `~~~${language.value}\n${codeContent.value}\n~~~`);

  const languageMeta = computed(() => {
    const lang = language.value.toLowerCase();

    if (
      lang === 'json' ||
      lang === 'toml' ||
      lang === 'xml' ||
      lang === 'yaml' ||
      lang === 'markdown'
    ) {
      return { label: lang, icon: LucideFileJson2, badgeClass: 'text-cyan-700 dark:text-cyan-300' };
    }
    if (
      lang === 'sql' ||
      lang === 'bash' ||
      lang === 'shell' ||
      lang === 'powershell' ||
      lang === 'batch'
    ) {
      return {
        label: lang,
        icon: LucideDatabase,
        badgeClass: 'text-emerald-700 dark:text-emerald-300',
      };
    }
    if (lang === 'python' || lang === 'ruby' || lang === 'php') {
      return {
        label: lang,
        icon: LucideSigma,
        badgeClass: 'text-fuchsia-700 dark:text-fuchsia-300',
      };
    }
    if (
      lang === 'html' ||
      lang === 'css' ||
      lang === 'scss' ||
      lang === 'graphql' ||
      lang === 'vue'
    ) {
      return {
        label: lang,
        icon: LucideFileCode2,
        badgeClass: 'text-orange-700 dark:text-orange-300',
      };
    }
    if (
      lang === 'javascript' ||
      lang === 'typescript' ||
      lang === 'jsx' ||
      lang === 'tsx' ||
      lang === 'cpp' ||
      lang === 'c' ||
      lang === 'csharp'
    ) {
      return {
        label: lang,
        icon: LucideBraces,
        badgeClass: 'text-indigo-700 dark:text-indigo-300',
      };
    }

    return { label: lang, icon: LucideBraces, badgeClass: 'text-zinc-700 dark:text-zinc-300' };
  });

  const copyCode = () => copyText(codeContent.value);

  return {
    copied,
    codeContent,
    isJsonBlock,
    language,
    markdown,
    languageMeta,
    copyCode,
  };
}
