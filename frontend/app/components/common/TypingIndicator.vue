<script setup lang="ts">
import { computed, toRef } from 'vue';
import type { MessageBlock } from '~/types/message';
import { useTypingIndicatorMatrix } from '~/composables/common/useTypingIndicatorMatrix';

const props = withDefaults(
  defineProps<{
    text?: string;
    label?: string;
    active?: boolean;
    block?: MessageBlock;
    loading?: boolean;
  }>(),
  {
    active: true,
  },
);

const { t } = useI18n();

const isReasoningBlock = computed(() => props.block?.type === 'reasoning');

const isVisible = computed(() => {
  if (!props.block) return true;
  if (!isReasoningBlock.value) return true;
  return Boolean(props.loading || props.block.isComplete === false);
});

const displayText = computed(() => props.text || t('reasoning.thinking'));

const accessibleLabel = computed(() => props.label || displayText.value);

const matrixActive = computed(() => {
  if (!props.active || !isVisible.value) return false;
  if (!props.block) return true;
  return Boolean(props.loading || props.block.isComplete === false);
});

const { size, gap, totalDots, activeDots } = useTypingIndicatorMatrix({
  active: matrixActive,
});
</script>

<template>
  <v-sheet
    v-if="isVisible"
    elevation="0"
    rounded="xl"
    class="inline-flex max-w-full items-center gap-3 bg-transparent px-0 py-0 text-neutral-500 dark:text-neutral-400"
    role="status"
    aria-live="polite"
  >
    <span class="sr-only">{{ accessibleLabel }}</span>
    <div
      class="grid size-4 shrink-0 text-neutral-500 dark:text-neutral-400"
      aria-hidden="true"
      :style="{
        gridTemplateColumns: `repeat(${size}, 1fr)`,
        gap: `${gap}px`,
      }"
    >
      <span
        v-for="i in totalDots"
        :key="i"
        class="rounded-sm bg-current transition-opacity duration-100"
        :class="activeDots.has(i - 1) ? 'opacity-100' : 'opacity-20'"
      />
    </div>
    <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ displayText }}</span>
  </v-sheet>
</template>
