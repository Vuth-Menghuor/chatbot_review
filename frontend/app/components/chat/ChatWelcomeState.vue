<script setup lang="ts">
import { computed, type Component } from 'vue';
import {
  CircleHelpIcon,
  FileTextIcon,
  ScanBarcodeIcon,
  TableIcon,
} from 'lucide-vue-next';

const { t } = useI18n();

interface WelcomeSuggestion {
  id: string;
  label: string;
  prompt: string;
  icon: Component;
}

const suggestions = computed<WelcomeSuggestion[]>(() => [
  {
    id: 'hsCode',
    label: t('chat.welcomeSuggestions.hsCode.label'),
    prompt: t('chat.welcomeSuggestions.hsCode.prompt'),
    icon: ScanBarcodeIcon,
  },
  {
    id: 'showDataAsChat',
    label: t('chat.welcomeSuggestions.showDataAsChat.label'),
    prompt: t('chat.welcomeSuggestions.showDataAsChat.prompt'),
    icon: TableIcon,
  },
  {
    id: 'askQuestion',
    label: t('chat.welcomeSuggestions.askQuestion.label'),
    prompt: t('chat.welcomeSuggestions.askQuestion.prompt'),
    icon: CircleHelpIcon,
  },
  {
    id: 'customsGuide',
    label: t('chat.welcomeSuggestions.customsGuide.label'),
    prompt: t('chat.welcomeSuggestions.customsGuide.prompt'),
    icon: FileTextIcon,
  },
]);

const emit = defineEmits<{
  'select-suggestion': [text: string];
}>();
</script>

<template>
  <div
    class="flex w-full flex-1 flex-col items-center justify-center px-4 text-center md:px-0 -mt-10 md:-mt-40"
  >
    <div class="mb-8 h-24 w-24">
      <v-img src="/logo/gdce-new-seal.png" alt="GDCE Seal" contain class="drop-shadow-sm" />
    </div>

    <h1 class="mb-10 text-xl font-bold tracking-tight text-gray-900 dark:text-zinc-100 md:text-3xl">
      {{ $t('chat.welcomeTitle') }}
    </h1>

    <div class="flex w-full max-w-3xl flex-wrap items-center justify-center gap-2.5">
      <button
        v-for="item in suggestions"
        :key="item.id"
        type="button"
        class="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        @click="emit('select-suggestion', item.prompt)"
      >
        <component :is="item.icon" class="h-4 w-4 shrink-0 opacity-80" aria-hidden="true" />
        <span class="whitespace-nowrap">{{ item.label }}</span>
      </button>
    </div>
  </div>
</template>
