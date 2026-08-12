<script setup lang="ts">
import type { Message } from '~/types/message';
import { useChatMessageRenderFlow } from '~/composables/chat/useChatMessageRenderFlow';
import ChatTypingIndicator from '../common/TypingIndicator.vue';

const props = defineProps<{
  message: Message;
  loading?: boolean;
  currentRenderType?: string;
  thinkingContext?: string;
}>();

const emit = defineEmits<{
  (e: 'regenerate', messageId: string): void;
  (e: 'user-reply', payload: { requestId: string; toolName?: string; action: string; values: Record<string, unknown> }): void;
}>();

const {
  anim,
  imageBlock,
  visibleBlocks,
  shouldShowTypingPhase,
  typingPhaseText,
  resolveRenderer,
  getTypingText,
  getBlockAnimId,
  isBlockLoading,
  shouldShowBlockTypingIndicator,
} = useChatMessageRenderFlow(props);
</script>

<template>
  <div class="flex flex-col gap-3 w-full">
    <!-- Image message: routed directly to ImageRenderer via synthetic block -->
    <component
      v-if="message.type === 'image' && imageBlock"
      :is="resolveRenderer('image')"
      :block="imageBlock"
      @regenerate="(id: string) => emit('regenerate', id)"
    />

    <!-- Text/rich blocks (Markdown, Charts, Tables, Workflow, etc.) -->
    <template v-else>
      <ChatTypingIndicator
        v-if="shouldShowTypingPhase"
        class="my-2"
        :text="typingPhaseText"
      />

      <TransitionGroup
        v-if="visibleBlocks.length"
        name="block-fade"
        tag="div"
        class="flex flex-col gap-3"
      >
        <template v-for="(block, index) in visibleBlocks" :key="block.id">
          <ChatTypingIndicator
            v-if="shouldShowBlockTypingIndicator(block, index)"
            class="my-2"
            :text="getTypingText(block)"
          />

          <component
            v-else
            :is="resolveRenderer(block.type)"
            :block="block"
            :loading="isBlockLoading(block, index)"
            :animate="anim.enabled"
            :anim-id="getBlockAnimId(block)"
            @regenerate="(id: string) => emit('regenerate', id)"
            @user-reply="(payload: { requestId: string; toolName?: string; action: string; values: Record<string, unknown> }) => emit('user-reply', payload)"
          />
        </template>
      </TransitionGroup>
    </template>
  </div>
</template>

<style scoped>
.block-fade-enter-active {
  transition: all 280ms ease;
}

.block-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
</style>
