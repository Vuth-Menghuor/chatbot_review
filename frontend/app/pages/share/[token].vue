<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ArrowLeftIcon } from 'lucide-vue-next';
import { getPublicChatShare } from '~/services/chat-api/chatShare';
import type { Message } from '~/types/message';

definePageMeta({
  layout: false,
});

const route = useRoute();
const runtimeConfig = useRuntimeConfig();
const token = computed(() => {
  const raw = route.params.token;
  return Array.isArray(raw) ? raw[0] : String(raw ?? '');
});

const title = ref('Shared chat');
const messages = ref<Message[]>([]);
const loading = ref(true);
const errorMessage = ref('');

onMounted(async () => {
  loading.value = true;
  errorMessage.value = '';
  try {
    const baseUrl = String(runtimeConfig.public.gdceApiBaseUrl ?? 'http://localhost:8000');
    const share = await getPublicChatShare(baseUrl, token.value);
    title.value = share.title || 'Shared chat';
    messages.value = share.messages ?? [];
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : 'This shared chat is unavailable.';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <v-app>
    <div class="flex h-screen min-h-0 flex-col overflow-hidden bg-white text-gray-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header
        class="flex h-14 shrink-0 items-center gap-3 border-b border-gray-100 px-4 dark:border-zinc-800"
      >
        <BaseIconButton :icon="ArrowLeftIcon" tooltip="Back to app" @click="navigateTo('/')" />
        <div class="min-w-0">
          <p class="truncate text-base font-semibold">{{ title }}</p>
          <p class="text-xs text-gray-500 dark:text-zinc-400">Shared chat</p>
        </div>
      </header>

      <main class="min-h-0 flex-1 overflow-hidden">
        <div v-if="loading" class="flex h-full items-center justify-center text-sm text-gray-500">
          Loading shared chat...
        </div>

        <BaseFriendlyErrorPanel
          v-else-if="errorMessage"
          class="mx-auto mt-10 max-w-xl"
          title="Shared chat unavailable"
          :message="errorMessage"
        />

        <ChatMessage
          v-else
          class="h-full"
          :messages="messages"
          :loading="false"
        />
      </main>
    </div>
  </v-app>
</template>
