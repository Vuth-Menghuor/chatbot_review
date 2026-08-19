<script setup lang="ts">
import { useChatList } from '~/composables';
import type { Message } from '~/types/message';
import ChatUser from './ChatUser.vue';
import ChatAssistant from './ChatAssistant.vue';
import ChatTypingIndicator from '../common/TypingIndicator.vue';

const props = defineProps<{
  messages: Message[];
  loading?: boolean;
  currentRenderType?: string;
}>();

const emit = defineEmits<{
  (e: 'scroll-status', payload: { isAtBottom: boolean }): void;
  (e: 'regenerate-image', messageId: string): void;
  (e: 'edit-user-message', messageId: string): void;
  (e: 'like', messageId: string): void;
  (e: 'dislike', messageId: string): void;
  (
    e: 'user-reply',
    payload: {
      requestId: string;
      toolName?: string;
      action: string;
      values: Record<string, unknown>;
    },
  ): void;
}>();

const { scrollContainer, scrollToBottom, isAtBottom } = useChatList(props, emit);

function getPreviousUserContent(index: number) {
  for (let i = index - 1; i >= 0; i -= 1) {
    const message = props.messages[i];
    if (message?.role === 'user') return message.content;
  }
  return '';
}

defineExpose({ scrollToBottom });
</script>

<template>
  <div ref="scrollContainer" class="relative h-full w-full overflow-y-auto custom-scrollbar">
    <div class="flex min-h-full flex-col">
      <div class="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-y-6 px-2 pt-2 sm:px-8 md:px-10">
        <div
          v-for="(msg, i) in messages"
          :key="msg.id ?? i"
          class="group flex w-full flex-col transition-all"
          :class="[msg.role === 'user' ? 'items-end' : 'items-start']"
        >
          <ChatUser
            v-if="msg.role === 'user'"
            :message="msg"
            :loading="i === messages.length - 1 ? loading : false"
            @edit="(messageId) => emit('edit-user-message', messageId)"
          />

          <ChatAssistant
            v-else
            :message="msg"
            :loading="i === messages.length - 1 ? loading : false"
            :current-render-type="i === messages.length - 1 ? currentRenderType : undefined"
            :thinking-context="getPreviousUserContent(i)"
            @regenerate-image="(id) => emit('regenerate-image', id)"
            @user-reply="(payload) => emit('user-reply', payload)"
            @like="(id) => emit('like', id)"
            @dislike="(id) => emit('dislike', id)"
          />
        </div>

        <!-- Typing indicator shown only when loading and no assistant content yet -->
        <Transition name="fade">
          <ChatTypingIndicator
            v-if="
              loading && (!messages.length || messages[messages.length - 1]?.role !== 'assistant')
            "
            :text="
              currentRenderType === 'thinking'
                ? 'Thinking...'
                : `Generating ${currentRenderType || 'response'}...`
            "
          />
        </Transition>
      </div>

      <div class="sticky bottom-0 z-30 w-full shrink-0">
        <CommonScrollToBottom :show="!isAtBottom" :loading="loading" @click="scrollToBottom" />
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
