<script setup lang="ts">
import { navigateTo, definePageMeta, useRoute } from '#imports';
import { useChatStore } from '~/stores/chat.store';
import { useAppLocale } from '~/composables/common/useAppLocale';

definePageMeta({ layout: 'default' });

const route = useRoute();
const chatStore = useChatStore();
const { t } = useAppLocale();

const handleSend = ({
  text,
  onResult,
}: {
  text: string;
  files?: File[];
  onResult?: (accepted: boolean) => void;
}) => {
  // New thread is only seeded with `?q=` (text). Attachments in this view are not carried over.
  if (!text.trim()) {
    onResult?.(false);
    return;
  }
  const projectQuery = route.query.project;
  const projectId =
    typeof projectQuery === 'string' && projectQuery.trim() ? projectQuery.trim() : undefined;
  // Create the chat entry with a temp title ("New Chat").
  // The real title is generated from the message inside useChat() when the first send fires.
  const chat = chatStore.createChat(t('chat.newChat'), projectId);
  onResult?.(true);
  navigateTo(`/chat/${chat.id}?q=${encodeURIComponent(text)}`);
};

const handleSuggestion = (text: string) => {
  handleSend({ text });
};
</script>

<template>
  <div
    class="flex flex-col h-full overflow-hidden bg-white w-full dark:bg-zinc-950 custom-scrollbar"
  >
    <!-- Welcome / empty state fills the available space -->
    <div class="flex min-h-0 flex-1 flex-col items-center justify-center overflow-hidden">
      <ChatWelcomeState @select-suggestion="handleSuggestion">
        <template #composer>
          <ChatInput :loading="false" :docked="false" @send="handleSend" />
        </template>
      </ChatWelcomeState>
    </div>
  </div>
</template>
