<script setup lang="ts">
import { computed } from 'vue';
import { SparklesIcon } from 'lucide-vue-next';

const { t } = useI18n();

interface WelcomeSuggestion {
  id: string;
  label: string;
  prompt: string;
}

const suggestions = computed<WelcomeSuggestion[]>(() => [
  {
    id: 'customsGuide',
    label: t('chat.welcomeSuggestions.customsGuide.label'),
    prompt: t('chat.welcomeSuggestions.customsGuide.prompt'),
  },
  {
    id: 'hsCode',
    label: t('chat.welcomeSuggestions.hsCode.label'),
    prompt: t('chat.welcomeSuggestions.hsCode.prompt'),
  },
  {
    id: 'askQuestion',
    label: t('chat.welcomeSuggestions.askQuestion.label'),
    prompt: t('chat.welcomeSuggestions.askQuestion.prompt'),
  },
  {
    id: 'showDataAsChat',
    label: t('chat.welcomeSuggestions.showDataAsChat.label'),
    prompt: t('chat.welcomeSuggestions.showDataAsChat.prompt'),
  },
]);

const emit = defineEmits<{
  'select-suggestion': [text: string];
}>();
</script>

<template>
  <div
    class="flex w-full flex-1 flex-col items-center justify-center px-4 pb-24 text-center sm:px-6 md:px-8 md:pb-32"
  >
    <div class="mb-5 h-32 w-32 select-none bg-transparent md:h-36 md:w-36">
      <v-img
        src="/logo/3d-ai-avatar-transparent.png"
        alt="Customs AI Avatar"
        contain
        draggable="false"
        class="chat-welcome-avatar bg-transparent"
        @dragstart.prevent
      />
    </div>

    <h1 class="mb-2 text-xl font-bold tracking-tight text-gray-900 dark:text-zinc-100 md:text-3xl">
      {{ $t('chat.welcomeTitle') }}
    </h1>
    <p class="mb-6 max-w-xl text-sm leading-6 text-gray-500 dark:text-zinc-400 md:text-base">
      {{ $t('chat.welcomeSubtitle') }}
    </p>

    <div v-if="$slots.composer" class="mb-7 w-full max-w-3xl">
      <slot name="composer" />
    </div>

    <div class="w-full max-w-3xl px-4 text-left sm:px-6">
      <div
        class="mb-4 flex items-center gap-1.5 px-1 text-sm font-semibold text-zinc-600 dark:text-zinc-300"
      >
        <SparklesIcon class="h-4 w-4 text-sky-500 dark:text-sky-400" aria-hidden="true" />
        <span>{{ $t('chat.welcomeSuggestions.heading') }}</span>
      </div>

      <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <button
          v-for="item in suggestions"
          :key="item.id"
          type="button"
          class="group flex min-h-12 w-full items-start gap-3 rounded-2xl bg-zinc-50 px-3.5 py-3 text-left text-sm leading-5 text-zinc-700 transition hover:bg-zinc-100 hover:text-zinc-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-200 dark:bg-zinc-900/60 dark:text-zinc-200 dark:hover:bg-zinc-900 dark:hover:text-white dark:focus-visible:ring-zinc-800"
          @click="emit('select-suggestion', item.prompt)"
        >
          <span
            class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 transition group-hover:bg-zinc-500 dark:bg-zinc-700 dark:group-hover:bg-zinc-400"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1">{{ item.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.chat-welcome-avatar img) {
  user-select: none;
  -webkit-user-drag: none;
}
</style>
