<template>
  <SettingsBlock :spy-id="'language'" :title="$t('settings.language.title')">
    <div
      class="grid grid-cols-2 gap-2 sm:gap-4"
      role="radiogroup"
      :aria-label="$t('settings.language.selectorLabel')"
    >
      <button
        v-for="option in languages"
        :key="option.id"
        type="button"
        role="radio"
        :aria-checked="activeLanguage === option.id"
        class="group flex min-w-0 flex-col items-center gap-2 rounded-lg p-0.5 text-center transition-opacity outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-950"
        @click="emit('update:activeLanguage', option.id)"
      >
        <LanguageOptionPreview
          :variant="option.id"
          :selected="activeLanguage === option.id"
        />

        <span
          class="w-full truncate text-xs font-medium text-gray-700 sm:text-sm dark:text-zinc-300"
          :class="activeLanguage === option.id ? 'text-gray-950 dark:text-white' : ''"
        >
          {{ $t(`settings.language.options.${option.id}`) }}
        </span>
      </button>
    </div>
  </SettingsBlock>
</template>

<script setup lang="ts">
import type { AppLanguage, AppLanguageOption } from '~/composables/useLanguages';
import LanguageOptionPreview from './LanguageOptionPreview.vue';

defineProps<{
  languages: readonly AppLanguageOption[];
  activeLanguage: AppLanguage;
}>();

const emit = defineEmits<{
  (e: 'update:activeLanguage', value: AppLanguage): void;
}>();
</script>
