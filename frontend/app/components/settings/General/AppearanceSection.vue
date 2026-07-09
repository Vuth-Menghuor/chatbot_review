<template>
  <SettingsBlock :spy-id="'appearance'" :title="$t('settings.appearance.title')">
    <div
      class="grid grid-cols-3 gap-2 sm:gap-4"
      role="radiogroup"
      :aria-label="$t('settings.appearance.title')"
    >
      <button
        v-for="option in appearanceOptions"
        :key="option.value"
        type="button"
        role="radio"
        :aria-checked="selectedTheme === option.value"
        class="group flex min-w-0 flex-col items-center gap-2 rounded-lg p-0.5 text-center transition-opacity outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-950"
        @click="selectedTheme = option.value"
      >
        <AppearanceThemePreview
          :variant="option.value"
          :selected="selectedTheme === option.value"
        />

        <span
          class="w-full truncate text-xs font-medium text-gray-700 sm:text-sm dark:text-zinc-300"
          :class="selectedTheme === option.value ? 'text-gray-950 dark:text-white' : ''"
        >
          {{ option.label }}
        </span>
      </button>
    </div>
  </SettingsBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AppThemeName } from '~/utils/theme/vuetifyThemes';
import { useAppearanceOptions } from '~/composables/settings/useAppearanceOptions';
import AppearanceThemePreview from './AppearanceThemePreview.vue';

const { theme, setTheme } = useAppTheme();
const { appearanceOptions } = useAppearanceOptions();

const selectedTheme = computed({
  get: () => theme.value,
  set: (value: AppThemeName) => setTheme(value),
});
</script>
