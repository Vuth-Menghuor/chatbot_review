<template>
  <section v-if="content.url" class="my-1">
    <p class="text-base leading-7 text-neutral-700 dark:text-neutral-300">
      For official verification, check the
      <a
        :href="content.url"
        target="_blank"
        rel="noopener noreferrer"
        class="md-link"
      >
        {{ content.label || content.title || 'GDCE tariff lookup' }}
      </a>.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { MessageBlock } from '~/types/message';

interface OfficialReferenceContent {
  title?: string;
  label?: string;
  url?: string;
  agency?: string | null;
  sourceType?: string | null;
}

const props = defineProps<{
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}>();

const content = computed<OfficialReferenceContent>(() => {
  if (!props.block.content || typeof props.block.content !== 'object' || Array.isArray(props.block.content)) {
    return {};
  }
  return props.block.content as OfficialReferenceContent;
});
</script>
