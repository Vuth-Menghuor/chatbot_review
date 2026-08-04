<template>
  <div
    ref="containerRef"
    class="markdown-body"
  >
    <div :key="mermaidRemountKey">
      <template v-for="section in parsedSections" :key="section.key">
        <div v-if="section.type === 'html'" v-html="section.content" />
        <TableRenderer
          v-else-if="section.type === 'table' && section.tableBlock"
          :block="section.tableBlock"
          :animate="!props.loading"
        />
        <ChartTaskRenderer
          v-else-if="section.type === 'chart' && section.chartBlock"
          :block="section.chartBlock"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useTheme } from 'vuetify';
import type { MessageBlock } from '../../types/message';
import {
  useMarkdown,
  useMarkdownCodeCopy,
  highlighterReady,
} from '~/composables/renderers/useMarkdownRenderer';
import { useMarkdownFenceHighlighter } from '~/composables/renderers/useMarkdownFenceHighlighter';
import { useTypewriter } from '~/composables/message/useTypewriter';
import { defaultTypingConfig } from '~/composables/message/typingDefaults';
import TableRenderer from '~/components/renderers/TableRenderer.vue';
import ChartTaskRenderer from '~/components/renderers/ChartTaskRenderer.vue';
import {
  areMermaidFencesExplicitlyClosed,
  hasMermaidFence,
  loadMermaid,
  normalizeLatexInMarkdown,
  normalizeMermaidLLMOutput,
  parseMarkdownSections,
} from '~/utils/markdown';
import { legacyToolContentToMarkdown } from '~/utils/tool/formulaToMarkdown';

const props = defineProps<{
  block: MessageBlock;
  loading?: boolean;
}>();

const { t, locale } = useI18n();
const { render } = useMarkdown();
const containerRef = ref<HTMLElement | null>(null);
const theme = useTheme();
const mermaidIsDark = computed(() => theme.global.current.value.dark);
const mermaidRemountKey = ref(0);

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

async function runMermaidInContainer() {
  if (typeof window === 'undefined') {
    return;
  }
  if (!areMermaidFencesExplicitlyClosed(displayText.value)) {
    return;
  }
  const root = containerRef.value;
  if (!root) {
    return;
  }
  const nodes = root.querySelectorAll<HTMLElement>('.mermaid:not([data-processed])');
  if (!nodes.length) {
    return;
  }
  const mermaid = await loadMermaid();
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    suppressErrorRendering: true,
    theme: mermaidIsDark.value ? 'dark' : 'default',
  });

  for (const element of Array.from(nodes)) {
    if (element.getAttribute('data-processed')) {
      continue;
    }

    let text = (element.textContent ?? '').trim();
    if (!text) {
      continue;
    }

    const normalized = normalizeMermaidLLMOutput(text);
    if (normalized !== text) {
      element.replaceChildren(document.createTextNode(normalized));
      text = normalized;
    }

    element.classList.remove('mermaid-source-only');
    const snapshot = text;

    try {
      await mermaid.run({ nodes: [element], suppressErrors: true });
    } catch {
      element.removeAttribute('data-processed');
      element.replaceChildren(document.createTextNode(snapshot));
      element.classList.add('mermaid', 'mermaid-source-only');
    }
  }
}

function scheduleMermaidRun() {
  if (typeof window === 'undefined') {
    return;
  }
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  const delay = props.loading ? 250 : 0;
  debounceTimer = setTimeout(async () => {
    debounceTimer = null;
    await nextTick();
    try {
      await runMermaidInContainer();
    } catch {
      /* invalid or partial diagrams during streaming */
    }
  }, delay);
}

const textTarget = computed(() => {
  const content = props.block.content;
  let base: string;
  if (typeof content === 'string') {
    base = content;
  } else {
    const legacy =
      legacyToolContentToMarkdown('calculator', content, locale.value) ??
      legacyToolContentToMarkdown('math', content, locale.value);
    if (legacy) {
      base = legacy;
    } else if (content && typeof content === 'object') {
      base = JSON.stringify(content, null, 2);
    } else {
      base = String(content ?? '');
    }
  }
  return normalizeLatexInMarkdown(base);
});

const typewriterEnabled = computed(() =>
  Boolean(!props.loading && props.block.meta?.typewriter === true),
);
const { typedText, flush: flushTypewriter } = useTypewriter(textTarget, typewriterEnabled, {
  config: defaultTypingConfig,
});

const displayText = computed(() => (props.loading ? textTarget.value : typedText.value));

watch(
  () => props.loading,
  (loading, wasLoading) => {
    if (wasLoading && !loading && hasMermaidFence(textTarget.value)) {
      flushTypewriter();
    }
  },
);

onMounted(() => {
  if (!props.loading && hasMermaidFence(textTarget.value)) {
    flushTypewriter();
  }
});

const sanitizedHtml = computed(() => {
  const _ = highlighterReady.value;
  return render(displayText.value);
});

const parsedSections = computed(() =>
  parseMarkdownSections(sanitizedHtml.value, {
    blockId: props.block.id,
    isComplete: !props.loading,
    onTableParseError: () => undefined,
  }),
);

watch(mermaidIsDark, () => {
  mermaidRemountKey.value += 1;
});

watch(
  [sanitizedHtml, () => props.loading, mermaidRemountKey],
  () => {
    scheduleMermaidRun();
  },
  { flush: 'post' },
);

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer);
});

useMarkdownCodeCopy(containerRef, {
  copyLabel: () => t('common.copy'),
  copiedLabel: () => t('common.copied'),
});
useMarkdownFenceHighlighter(containerRef, mermaidIsDark, sanitizedHtml);
</script>

<style scoped>
.markdown-body {
  transition: opacity 180ms ease;
}

.markdown-body :deep(.shiki-markdown-wrap pre) {
  margin: 0;
  padding: 0;
  overflow-x: auto;
  background-color: transparent !important;
  font-family: var(--font-family-app);
  font-size: 0.875rem;
  line-height: 1.6;
}

.markdown-body :deep(.shiki-markdown-wrap .shiki) {
  background-color: transparent !important;
}

.markdown-body :deep(.md-limitation-note) {
  margin-top: 1rem;
  margin-bottom: 0.75rem;
  border: 1px solid rgb(251 191 36 / 0.45);
  border-radius: 0.625rem;
  background: rgb(255 251 235 / 0.9);
  padding: 0.875rem 1rem;
  color: rgb(120 53 15);
  font-style: normal;
}

.markdown-body :deep(.md-limitation-note::before) {
  display: block;
  margin-bottom: 0.375rem;
  color: rgb(146 64 14);
  content: 'Information limitation';
  font-size: 0.8125rem;
  font-weight: 700;
}

:global(.dark) .markdown-body :deep(.md-limitation-note) {
  border-color: rgb(146 64 14 / 0.6);
  background: rgb(69 26 3 / 0.35);
  color: rgb(253 230 138);
}

:global(.dark) .markdown-body :deep(.md-limitation-note::before) {
  color: rgb(252 211 77);
}

.markdown-body :deep(.calculator-section-heading) {
  margin-top: 2rem;
  margin-bottom: 1rem;
  border-top: 1px solid rgb(229 231 235);
  padding-top: 1.25rem;
  color: rgb(17 24 39);
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.45;
}

.markdown-body :deep(h2.calculator-section-heading) {
  margin-top: 2.25rem;
  margin-bottom: 1.25rem;
  padding-top: 1.5rem;
  font-size: 1.25rem;
}

.markdown-body :deep(.calculator-section-heading + .md-paragraph) {
  margin-top: 0;
}

.markdown-body :deep(.calculator-section-heading + .md-list) {
  margin-top: 0;
}

:global(.dark) .markdown-body :deep(.calculator-section-heading) {
  border-top-color: rgb(39 39 42);
  color: rgb(245 245 245);
}
</style>
