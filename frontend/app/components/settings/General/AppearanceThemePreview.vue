<template>
  <div
    class="appearance-theme-preview w-full overflow-hidden rounded-xl transition-shadow"
    :class="
      selected
        ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-white dark:ring-offset-zinc-950'
        : 'ring-1 ring-gray-200/80 dark:ring-zinc-700/80'
    "
  >
    <!-- Light -->
    <div
      v-if="variant === 'light'"
      class="aspect-5/4 w-full bg-linear-to-b from-sky-300 via-sky-200 to-emerald-100 p-2 sm:p-2.5"
    >
      <div class="flex h-full flex-col overflow-hidden rounded-md bg-white shadow-sm">
        <div class="flex items-center gap-1 border-b border-gray-200 bg-gray-100 px-1.5 py-1">
          <span class="h-1.5 w-1.5 rounded-full bg-[#ff5f57]" aria-hidden="true" />
          <span class="h-1.5 w-1.5 rounded-full bg-[#febc2e]" aria-hidden="true" />
          <span class="h-1.5 w-1.5 rounded-full bg-[#28c840]" aria-hidden="true" />
          <span class="ml-1 h-1 flex-1 rounded-sm bg-gray-200" aria-hidden="true" />
        </div>
        <div class="flex flex-1 flex-col gap-1 p-1.5">
          <span class="h-1 w-2/3 rounded-sm bg-gray-100" aria-hidden="true" />
          <span class="h-1 w-1/2 rounded-sm bg-gray-100" aria-hidden="true" />
          <span class="mt-auto h-4 w-full rounded-sm bg-gray-50" aria-hidden="true" />
        </div>
      </div>
    </div>

    <!-- Dark -->
    <div
      v-else-if="variant === 'dark'"
      class="aspect-5/4 w-full bg-linear-to-b from-zinc-700 via-zinc-800 to-zinc-950 p-2 sm:p-2.5"
    >
      <div class="flex h-full flex-col overflow-hidden rounded-md bg-zinc-900 shadow-sm">
        <div class="flex items-center gap-1 border-b border-zinc-800 bg-zinc-800 px-1.5 py-1">
          <span class="h-1.5 w-1.5 rounded-full bg-[#ff5f57]" aria-hidden="true" />
          <span class="h-1.5 w-1.5 rounded-full bg-[#febc2e]" aria-hidden="true" />
          <span class="h-1.5 w-1.5 rounded-full bg-[#28c840]" aria-hidden="true" />
          <span class="ml-1 h-1 flex-1 rounded-sm bg-zinc-700" aria-hidden="true" />
        </div>
        <div class="flex flex-1 flex-col gap-1 p-1.5">
          <span class="h-1 w-2/3 rounded-sm bg-zinc-800" aria-hidden="true" />
          <span class="h-1 w-1/2 rounded-sm bg-zinc-800" aria-hidden="true" />
          <span class="mt-auto h-4 w-full rounded-sm bg-zinc-950" aria-hidden="true" />
        </div>
      </div>
    </div>

    <!-- Custom (split light / dark preview) -->
    <div v-else class="relative aspect-5/4 w-full overflow-hidden">
      <div class="absolute inset-0 flex">
        <div class="flex w-1/2 flex-col bg-linear-to-b from-sky-300 to-emerald-100 p-1.5 sm:p-2">
          <div
            class="flex h-full flex-col overflow-hidden rounded-md rounded-r-none bg-white shadow-sm"
          >
            <div class="flex items-center gap-0.5 bg-gray-100 px-1 py-0.5">
              <span class="h-1 w-1 rounded-full bg-[#ff5f57]" aria-hidden="true" />
              <span class="h-1 w-1 rounded-full bg-[#febc2e]" aria-hidden="true" />
              <span class="h-1 w-1 rounded-full bg-[#28c840]" aria-hidden="true" />
            </div>
            <div class="flex-1 bg-white" aria-hidden="true" />
          </div>
        </div>
        <div class="flex w-1/2 flex-col bg-linear-to-b from-zinc-700 to-zinc-950 p-1.5 sm:p-2">
          <div
            class="flex h-full flex-col overflow-hidden rounded-md rounded-l-none bg-zinc-900 shadow-sm"
          >
            <div class="flex items-center gap-0.5 bg-zinc-800 px-1 py-0.5">
              <span class="h-1 w-1 rounded-full bg-[#ff5f57]" aria-hidden="true" />
              <span class="h-1 w-1 rounded-full bg-[#febc2e]" aria-hidden="true" />
              <span class="h-1 w-1 rounded-full bg-[#28c840]" aria-hidden="true" />
            </div>
            <div class="flex-1 bg-zinc-950" aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AppThemeName } from '~/utils/theme/vuetifyThemes';

defineProps<{
  variant: AppThemeName;
  selected?: boolean;
}>();
</script>
