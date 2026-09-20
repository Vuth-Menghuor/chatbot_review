<script setup lang="ts">
import { ref, onMounted, watch, computed, nextTick } from 'vue';
import { useRoute, useRouter, definePageMeta, navigateTo } from '#imports';
import { storeToRefs } from 'pinia';
import { useChat } from '~/composables';
import { useChatStore } from '~/stores/chat.store';

definePageMeta({
  layout: 'default',
  key: (route) => String(route.params.id),
});

const route = useRoute();
const router = useRouter();
const rawParam = route.params.id;
const chatId = (Array.isArray(rawParam) ? rawParam[0] : rawParam) as string;
const chatStore = useChatStore();
const { recentChats } = storeToRefs(chatStore);

const currentChatInStore = computed(() => recentChats.value.some((c) => c.id === chatId));
const chatListRef = ref<{ scrollToBottom?: (behavior?: ScrollBehavior) => Promise<void> } | null>(
  null,
);
const chatInputRef = ref<{ setDraft?: (text: string) => Promise<void> | void } | null>(null);

const { messages, loading, currentRenderType, send, sendUserReply, stop, regenerate, loadServerHistory } =
  useChat(chatId);

const scrollToBottom = (behavior: ScrollBehavior = 'smooth') =>
  chatListRef.value?.scrollToBottom?.(behavior);

const handleSendMessage = async ({
  text,
  files,
  onResult,
}: {
  text: string;
  files?: File[];
  onResult?: (accepted: boolean) => void;
}) => {
  await nextTick();
  await scrollToBottom('instant');
  const restoreComposer = await send(text, files);
  await nextTick();
  await scrollToBottom('instant');
  onResult?.(!restoreComposer);
};

const handleStop = () => stop();

const handleEditUserMessage = async (messageId: string) => {
  const target = messages.value.find(
    (message) => message.role === 'user' && message.id === messageId,
  );
  if (!target?.content?.trim()) return;
  await chatInputRef.value?.setDraft?.(target.content);
};

function handleLike(messageId: string) {
  const message = messages.value.find((item) => String(item.id) === String(messageId));

  if (!message) return;

  message.feedback = message.feedback === 'like' ? null : 'like';
}

function handleDislike(messageId: string) {
  const message = messages.value.find((item) => String(item.id) === String(messageId));

  if (!message) return;

  message.feedback = message.feedback === 'dislike' ? null : 'dislike';
}

watch(currentChatInStore, (inStore, wasInStore) => {
  if (wasInStore && !inStore) {
    void navigateTo('/');
  }
});

onMounted(async () => {
  await nextTick();
  if (!currentChatInStore.value && !chatStore.hydrateChatIfMessagesExist(chatId)) {
    await navigateTo('/');
    return;
  }

  await loadServerHistory();

  const pendingText = route.query.q as string | undefined;
  if (pendingText?.trim()) {
    router.replace({ query: {} });
    await scrollToBottom('instant');
    await send(pendingText);
    await nextTick();
    await scrollToBottom('instant');
  }
});
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden bg-white dark:bg-zinc-950">
    <ChatMessage
      ref="chatListRef"
      class="min-h-0 flex-1"
      :messages="messages"
      :loading="loading"
      :current-render-type="currentRenderType"
      @regenerate-image="() => regenerate()"
      @edit-user-message="handleEditUserMessage"
      @user-reply="(payload) => sendUserReply(payload)"
      @like="handleLike"
      @dislike="handleDislike"
    >
      <template #footer>
        <ChatInput
          ref="chatInputRef"
          :loading="loading"
          docked
          @send="handleSendMessage"
          @stop="handleStop"
        />
      </template>
    </ChatMessage>
  </div>
</template>
