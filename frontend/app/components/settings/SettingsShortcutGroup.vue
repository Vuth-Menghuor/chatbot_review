<template>
  <section :data-settings-spy="spyId" class="space-y-3 scroll-mt-20">
    <h3 class="settings-section-title px-1">{{ $t(titleKey) }}</h3>

    <div class="settings-panel">
      <template v-for="(item, index) in items" :key="item.id">
        <div class="flex items-center justify-between gap-3 px-4 py-2.5">
          <span class="min-w-0 flex-1 truncate text-base text-high-emphasis dark:text-zinc-100">
            {{ item.label }}
          </span>

          <kbd
            v-if="item.keys"
            class="inline-flex shrink-0 items-center whitespace-nowrap rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 font-mono text-[11px] text-white dark:border-zinc-300 dark:bg-zinc-100 dark:text-black"
          >
            {{ item.keys }}
          </kbd>
        </div>

        <div
          v-if="index < items.length - 1"
          class="mx-4 border-t border-gray-100 dark:border-zinc-800"
        />
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { KeyboardShortcutRow } from '~/composables/keyboard/useKeyboardShortcutCatalog';

defineProps<{
  spyId: string;
  titleKey: string;
  items: KeyboardShortcutRow[];
}>();
</script>
