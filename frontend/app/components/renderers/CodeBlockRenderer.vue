<script setup lang="ts">
import { ref, computed, toRef, watchEffect, onMounted } from 'vue';
import { useTheme } from 'vuetify';
import type { MessageBlock } from '../../types/message';
import { useCodeBlockRenderer } from '~/composables/renderers/useCodeRenderer';
import { highlightCode } from '~/utils/code';

const props = defineProps<{
  block: MessageBlock;
  loading?: boolean;
}>();

const { codeContent, language, languageMeta } = useCodeBlockRenderer(toRef(props, 'block'));
const theme = useTheme();
const isDark = computed(() => theme.global.current.value.dark);

const highlightedHtml = ref<string>('');
const isHighlighting = ref(false);

let highlightRunId = 0;

const updateHighlight = async () => {
  const runId = ++highlightRunId;
  isHighlighting.value = true;
  try {
    let html = await highlightCode(
      codeContent.value,
      language.value,
      isDark.value ? 'dark' : 'light',
    );
    // Force transparency by removing Shiki's inline background-color
    html = html.replace(/background-color:\s*#[0-9a-fA-F]+;?/, 'background-color: transparent;');
    if (runId !== highlightRunId) return;
    highlightedHtml.value = html;
  } finally {
    if (runId === highlightRunId) {
      isHighlighting.value = false;
    }
  }
};

watchEffect(() => {
  updateHighlight();
});

onMounted(() => {
  updateHighlight();
});
</script>

<template>
  <div
    class="code-block-renderer rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-800 group/code"
  >
    <!-- Header with Label & Copy -->
    <div
      class="bg-neutral-100 dark:bg-neutral-800/60 px-4 text-xs font-mono text-neutral-600 dark:text-neutral-300 flex justify-between items-center border-b border-neutral-200 dark:border-neutral-700"
    >
      <div class="flex items-center gap-2">
        <component :is="languageMeta.icon" class="size-5 text-black dark:text-white" />
        <span class="uppercase tracking-widest font-bold">
          {{ languageMeta.label }}
        </span>
      </div>
      <BaseCopy
        :content="codeContent"
        button-variant="plain"
        custom-class="text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
      />
    </div>

    <!-- Highlighted Code -->
    <div
      v-if="highlightedHtml && !loading"
      v-html="highlightedHtml"
      class="shiki-container bg-neutral-100 dark:bg-zinc-900/40"
    />
    <div
      v-else
      class="p-4 bg-neutral-100 dark:bg-zinc-900/40 animate-pulse h-32 flex items-center justify-center"
    >
      <v-progress-circular indeterminate size="20" width="2" color="primary" />
    </div>
  </div>
</template>

<style scoped>
.shiki-container :deep(pre) {
  margin: 0;
  padding: 1.25rem;
  overflow-x: auto;
  background-color: transparent !important;
  font-family: var(--font-family-app);
  font-size: 0.875rem;
  line-height: 1.6;
}

.shiki-container :deep(.shiki) {
  background-color: transparent !important;
}

.shiki-container :deep(code) {
  counter-reset: line;
}
</style>
