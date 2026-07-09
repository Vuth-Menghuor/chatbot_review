<template>
  <v-tooltip
    v-bind="$attrs"
    :location="location"
    :offset="offset"
    :activator="$slots.default ? undefined : 'parent'"
    content-class="base-tooltip-content"
  >
    <template v-if="$slots.default" #activator="{ props: activatorProps }">
      <div v-bind="activatorProps" class="inline-block">
        <slot />
      </div>
    </template>

    <div
      class="rounded-md bg-gray-900 px-2 py-1 text-[14px] leading-7 text-white shadow-sm dark:bg-zinc-200 dark:text-zinc-900"
    >
      {{ text }}
    </div>
  </v-tooltip>
</template>

<script setup lang="ts">
import type { TooltipLocation } from '~/types/message';

interface Props {
  text: string;
  location?: TooltipLocation;
  offset?: number | string;
}

withDefaults(defineProps<Props>(), {
  location: 'bottom',
  offset: 4,
});
</script>

<style>
/* Let the inner bubble control colors in light and dark mode */
.base-tooltip-content {
  background: transparent !important;
  padding: 0 !important;
  box-shadow: none !important;
  color: inherit;
}
</style>
