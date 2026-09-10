import { onBeforeUnmount, onMounted, shallowRef, type Ref, ref } from 'vue';
import MarkdownIt from 'markdown-it';
import type Token from 'markdown-it/lib/token.mjs';
import type { RenderRule } from 'markdown-it/lib/renderer.mjs';
import DOMPurify from 'dompurify';
import type { Config } from 'dompurify';
import { getHighlighterInstance } from '~/utils/code';
import { useClipboardCopy } from '~/composables/common/useClipboardCopy';
import { tryParseJsonLike } from '~/utils/json';
import { chartToolRequestToBlockContent } from '~/utils/tool/chartToolRequestPreview';

export const highlighterReady = ref(false);

// Initialize highlighter once
if (typeof window !== 'undefined') {
  getHighlighterInstance().then(() => {
    highlighterReady.value = true;
  });
}

/** Keep diagram placeholders and markdown output consistent with custom fence HTML. */
const MARKDOWN_PURIFY_CONFIG: Config = {
  ADD_ATTR: [
    'class',
    'id',
    'data-table',
    'data-chart',
    'data-code',
    'type',
    'aria-label',
    'aria-hidden',
    'title',
    'target',
    'rel',
  ],
};

function fenceLanguageLabel(langKey: string): string {
  if (!langKey || langKey === 'code') return 'CODE';
  return langKey.toUpperCase();
}

const FENCE_COPY_ICON_HTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="copy-btn-icon" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`;

const FENCE_CHECK_ICON_HTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="copy-btn-icon" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>`;

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true,
}).enable(['table', 'strikethrough', 'code', 'fence']);

function isLimitationParagraph(tokens: Token[], idx: number) {
  const inline = tokens[idx + 1];
  if (!inline || inline.type !== 'inline') return false;
  const text = inline.content.toLowerCase();
  const hasLimitationSignal =
    text.includes('provided context') ||
    text.includes('available context') ||
    text.includes('provided documentation') ||
    text.includes('available documentation') ||
    text.includes('provided documents') ||
    text.includes('available documents') ||
    text.includes('available sources') ||
    text.includes('provided sources');
  const hasIncompleteSignal =
    text.includes('do not include') ||
    text.includes('does not include') ||
    text.includes('do not contain') ||
    text.includes('does not contain') ||
    text.includes('do not provide') ||
    text.includes('does not provide') ||
    text.includes('not include') ||
    text.includes('not exhaustive') ||
    text.includes('comprehensive checklist') ||
    text.includes('complete checklist');
  return hasLimitationSignal && hasIncompleteSignal;
}

// Custom rules configuration (defined once)
const tableOpenRule: RenderRule = (tokens, idx, options, env, self) => {
  let nextIdx = idx + 1;
  const columns: { key: string; title: string }[] = [];
  const rows: Record<string, string>[] = [];

  let inThead = false;
  let inTbody = false;
  let currentTableRow: Record<string, string> = {};
  let currentCellIndex = 0;

  while (nextIdx < tokens.length) {
    const token = tokens[nextIdx]!;
    if (token.type === 'table_close') {
      break;
    }

    if (token.type === 'thead_open') {
      inThead = true;
    } else if (token.type === 'thead_close') {
      inThead = false;
    } else if (token.type === 'tbody_open') {
      inTbody = true;
    } else if (token.type === 'tbody_close') {
      inTbody = false;
    } else if (token.type === 'tr_open') {
      currentCellIndex = 0;
      currentTableRow = {};
    } else if (token.type === 'tr_close') {
      if (inTbody) {
        rows.push(currentTableRow);
      }
    } else if (token.type === 'inline') {
      const contentHtml = token.children
        ? self.renderInline(token.children, options, env)
        : token.content;
      if (inThead) {
        const key = `col_${columns.length}`;
        columns.push({ key, title: contentHtml });
      } else if (inTbody) {
        const col = columns[currentCellIndex];
        if (col) {
          currentTableRow[col.key] = contentHtml;
        }
        currentCellIndex++;
      }
    }

    nextIdx++;
  }

  // Rewrite all internal table tokens to be skipped so markdown-it outputs empty strings for them
  for (let i = idx + 1; i <= nextIdx; i++) {
    tokens[i]!.type = 'table_skipped';
  }

  const tableData = { columns, rows };
  const serialized = encodeURIComponent(JSON.stringify(tableData));
  return `<div class="custom-markdown-table-placeholder" data-table="${serialized}"></div>`;
};

md.renderer.rules.table_open = tableOpenRule;

md.renderer.rules.table_skipped = () => '';
md.renderer.rules.table_close = () => '';

md.renderer.rules.code_inline = (tokens: Token[], idx: number) =>
  `<code class="md-inline-code">${md.utils.escapeHtml(tokens[idx]!.content)}</code>`;

// Linkify already converts markdown links, bare URLs, and email addresses.
// Give all of them a visible, consistent treatment and keep external
// navigation from replacing the chat page.
md.renderer.rules.link_open = (tokens: Token[], idx: number, options, env, self) => {
  const token = tokens[idx]!;
  token.attrJoin('class', 'md-link');
  token.attrSet('target', '_blank');
  token.attrSet('rel', 'noopener noreferrer');
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.fence = (tokens: Token[], idx: number) => {
  const token = tokens[idx]!;
  const rawInfo = token.info.trim();
  const langKey = (rawInfo.split(/\s/)[0] || 'code').toLowerCase();

  if (langKey === 'mermaid') {
    const escaped = md.utils.escapeHtml(token.content);
    return `<div class="mermaid-diagram-wrap my-3 rounded-lg overflow-x-auto border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/40 p-4"><pre class="mermaid">${escaped}</pre></div>`;
  }

  if (langKey === 'json' || langKey === 'code') {
    const parsed = tryParseJsonLike(token.content.trim());
    const chartContent = chartToolRequestToBlockContent(parsed);
    if (chartContent) {
      const serialized = encodeURIComponent(JSON.stringify(chartContent));
      return `<div class="custom-markdown-chart-placeholder" data-chart="${serialized}"></div>`;
    }
  }

  const code = md.utils.escapeHtml(token.content);
  const encoded = encodeURIComponent(token.content);
  const label = fenceLanguageLabel(langKey);

  return `<div class="markdown-code-fence my-6 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-800 group/code" data-fence-lang="${md.utils.escapeHtml(langKey)}" data-fence-code="${encoded}">
    <div class="bg-neutral-100 dark:bg-neutral-800/60 px-4 py-2 text-xs font-mono text-neutral-600 dark:text-neutral-300 flex justify-between items-center border-b border-neutral-200 dark:border-neutral-700">
      <span class="uppercase tracking-widest font-bold">${label}</span>
      <button
        type="button"
        class="copy-btn inline-flex items-center justify-center rounded-md p-1.5 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-200/60 dark:hover:bg-neutral-700/50 transition-colors"
        data-code="${encoded}"
        aria-label="Copy code"
        title="Copy code"
      >${FENCE_COPY_ICON_HTML}</button>
    </div>
    <div class="shiki-markdown-wrap bg-neutral-100 dark:bg-zinc-900/40 p-4 overflow-x-auto">
      <pre class="!m-0 !bg-transparent"><code class="language-${md.utils.escapeHtml(langKey)}">${code}</code></pre>
    </div>
  </div>`;
};

md.renderer.rules.paragraph_open = (tokens: Token[], idx: number) =>
  isLimitationParagraph(tokens, idx)
    ? '<p class="md-paragraph md-limitation-note">'
    : '<p class="md-paragraph">';
md.renderer.rules.heading_open = (tokens: Token[], idx: number) => {
  const level = tokens[idx]!.tag;
  const inline = tokens[idx + 1];
  const headingText = inline?.type === 'inline' ? inline.content : '';
  const calculatorHeading =
    headingText === 'Import Tax Calculation' ||
    headingText === 'Product Information' ||
    headingText === 'Input Parameters' ||
    headingText === 'Summary' ||
    headingText === 'Assumptions & Notes' ||
    headingText === 'References & Citations' ||
    headingText === 'Data Sources' ||
    /^Step \d+:/.test(headingText);
  if (calculatorHeading) {
    return `<${level} class="calculator-section-heading">`;
  }

  const sizes: Record<string, string> = {
    h1: 'text-2xl font-bold mt-8 mb-4 border-b border-neutral-200 dark:border-neutral-800 pb-2 text-neutral-900 dark:text-neutral-100',
    h2: 'text-xl font-bold mt-8 mb-4 text-neutral-900 dark:text-neutral-100',
    h3: 'text-lg font-bold mt-6 mb-3 text-neutral-900 dark:text-neutral-100',
  };
  return `<${level} class="${sizes[level] || ''}">`;
};

md.renderer.rules.bullet_list_open = (tokens: Token[], idx: number) => {
  const isNested = tokens[idx]!.level > 0;
  return `<ul class="md-list list-disc pl-6 ${isNested ? 'md-list-nested' : ''}">`;
};
md.renderer.rules.ordered_list_open = (tokens: Token[], idx: number) => {
  const isNested = tokens[idx]!.level > 0;
  return `<ol class="md-list list-decimal pl-6 ${isNested ? 'md-list-nested' : ''}">`;
};
md.renderer.rules.list_item_open = () => '<li class="md-list-item">';

md.renderer.rules.blockquote_open = () =>
  '<blockquote class="my-5 pl-5 border-l-4 border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/50 rounded-lg py-4 pr-4 italic text-neutral-600 dark:text-neutral-400 text-base leading-7">';

md.renderer.rules.hr = () =>
  '<hr class="my-8 border-t border-neutral-200 dark:border-neutral-800" />';

/**
 * Composable for Markdown rendering logic
 * Centralizes markdown-it configuration and custom render rules
 */
export function useMarkdown() {
  const render = (content: string) => {
    if (!content) return '';
    const raw = md.render(content);

    // DOMPurify is safe here as ssr is false and it's imported at top-level
    if (DOMPurify && typeof DOMPurify.sanitize === 'function') {
      return DOMPurify.sanitize(raw, MARKDOWN_PURIFY_CONFIG);
    }
    return raw;
  };

  return {
    md,
    render,
    initPurify: async () => {}, // No-op for compatibility
    dompurify: shallowRef(DOMPurify),
  };
}

export function useMarkdownCodeCopy(
  containerRef: Ref<HTMLElement | null>,
  labels?: { copyLabel?: () => string; copiedLabel?: () => string },
) {
  const { copyText } = useClipboardCopy();
  let resetTimer: ReturnType<typeof setTimeout> | null = null;

  const clearResetTimer = () => {
    if (!resetTimer) return;
    clearTimeout(resetTimer);
    resetTimer = null;
  };

  const handleClick = async (event: MouseEvent) => {
    const button = (event.target as HTMLElement | null)?.closest<HTMLButtonElement>('.copy-btn');
    if (!button || !containerRef.value?.contains(button)) return;

    const encoded = button.getAttribute('data-code');
    if (!encoded) return;

    let code = encoded;
    try {
      code = decodeURIComponent(encoded);
    } catch {
      // keep raw attribute if not URI-encoded
    }

    try {
      const copied = await copyText(code);
      if (!copied) return;

      const copyLabel = labels?.copyLabel?.() || 'Copy code';
      const copiedLabel = labels?.copiedLabel?.() || 'Copied';
      const originalIconHtml = button.innerHTML;

      button.innerHTML = FENCE_CHECK_ICON_HTML;
      button.setAttribute('aria-label', copiedLabel);
      button.setAttribute('title', copiedLabel);

      clearResetTimer();
      resetTimer = setTimeout(() => {
        button.innerHTML = originalIconHtml || FENCE_COPY_ICON_HTML;
        button.setAttribute('aria-label', copyLabel);
        button.setAttribute('title', copyLabel);
      }, 2000);
    } catch {
      // Clipboard access may be blocked by browser permissions.
    }
  };

  onMounted(() => {
    containerRef.value?.addEventListener('click', handleClick);
  });

  onBeforeUnmount(() => {
    clearResetTimer();
    containerRef.value?.removeEventListener('click', handleClick);
  });
}
