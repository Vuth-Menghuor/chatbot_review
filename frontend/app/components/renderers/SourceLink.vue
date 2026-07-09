<script setup lang="ts">
import { computed } from 'vue';
import { ExternalLinkIcon } from 'lucide-vue-next';

const props = defineProps<{
  href?: string;
  title?: string;
}>();

const linkHref = computed(() => props.href || undefined);
const domain = computed(() => {
  if (!props.href) return '';
  try {
    return new URL(props.href).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
});
</script>

<template>
  <!-- Linked chip -->
  <v-btn
    v-if="linkHref"
    :href="linkHref"
    target="_blank"
    rel="noopener noreferrer"
    variant="outlined"
    size="x-small"
    rounded="pill"
    class="normal-case tracking-normal font-medium text-xs border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-300 px-2"
    :title="title || linkHref"
  >
    <!-- Favicon -->
    <template #prepend>
      <img
        v-if="domain"
        :src="`https://www.google.com/s2/favicons?domain=${domain}&sz=16`"
        :alt="domain"
        class="w-3.5 h-3.5 rounded-sm"
        @error="($event.target as HTMLImageElement).style.display = 'none'"
      />
    </template>
    <span class="truncate max-w-[160px]">
      <slot>{{ title || domain || linkHref }}</slot>
    </span>
    <template #append>
      <ExternalLinkIcon :size="10" class="opacity-50" />
    </template>
  </v-btn>

  <!-- Non-linked plain chip -->
  <v-chip
    v-else
    size="small"
    variant="outlined"
    class="text-xs font-medium text-neutral-500 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700"
  >
    <slot>Source</slot>
  </v-chip>
</template>
