<template>
  <div
    class="language-option-preview w-full overflow-hidden rounded-xl transition-shadow"
    :class="selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-white dark:ring-offset-zinc-950' : 'ring-1 ring-gray-200/80 dark:ring-zinc-700/80'"
  >
    <!-- English -->
    <div
      v-if="variant === 'en'"
      class="aspect-5/4 w-full bg-linear-to-b from-slate-100 via-sky-50 to-white p-2 sm:p-2.5 dark:from-zinc-800 dark:via-zinc-900 dark:to-zinc-950"
    >
      <div class="flex h-full flex-col overflow-hidden rounded-md border border-gray-200 bg-white shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
        <div class="border-b border-gray-100 px-2 py-1.5 dark:border-zinc-800">
          <span class="text-[0.5rem] font-semibold uppercase tracking-wide text-gray-400 dark:text-zinc-500">
            EN
          </span>
        </div>
        <div class="flex flex-1 flex-col justify-center gap-1 px-2 py-1.5">
          <p class="truncate text-[0.625rem] font-semibold leading-tight text-gray-900 sm:text-xs dark:text-zinc-100">
            Hello
          </p>
          <p class="truncate text-[0.5rem] leading-tight text-gray-500 sm:text-[0.625rem] dark:text-zinc-400">
            How can I help you today?
          </p>
        </div>
      </div>
    </div>

    <!-- Khmer -->
    <div
      v-else
      class="aspect-5/4 w-full bg-linear-to-b from-amber-50 via-orange-50/80 to-white p-2 sm:p-2.5 dark:from-zinc-800 dark:via-zinc-900 dark:to-zinc-950"
    >
      <div class="flex h-full flex-col overflow-hidden rounded-md border border-gray-200 bg-white shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
        <div class="border-b border-gray-100 px-2 py-1.5 dark:border-zinc-800">
          <span class="text-[0.5rem] font-semibold uppercase tracking-wide text-gray-400 dark:text-zinc-500">
            KM
          </span>
        </div>
        <div class="flex flex-1 flex-col justify-center gap-1 px-2 py-1.5 font-[Siemreap,'Noto_Sans_Khmer',sans-serif]">
          <p class="truncate text-[0.625rem] font-semibold leading-tight text-gray-900 sm:text-xs dark:text-zinc-100">
            សួស្តី
          </p>
          <p class="truncate text-[0.5rem] leading-tight text-gray-500 sm:text-[0.625rem] dark:text-zinc-400">
            តើខ្ញុំអាចជួយអ្នកបានយ៉ាងដូចម្តេច?
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AppLanguage } from '~/composables/useLanguages';

defineProps<{
  variant: AppLanguage;
  selected?: boolean;
}>();
</script>
