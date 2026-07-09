<script setup lang="ts">
import { ArrowUpIcon, SquircleIcon } from 'lucide-vue-next';
import BaseIconButton from '~/components/base/BaseIconButton.vue';

defineProps<{
  disabled?: boolean;
  loading?: boolean;
}>();

defineEmits<{
  (e: 'click'): void;
  (e: 'stop'): void;
}>();
</script>

<template>
  <BaseIconButton
    v-bind="$attrs"
    :icon="loading ? SquircleIcon : ArrowUpIcon"
    :disabled="!loading && disabled"
    :loading="false"
    variant="flat"
    size="default"
    width="36"
    height="36"
    :custom-class="
      [
        'chat-send-button',
        '!rounded-full shrink-0 flex items-center justify-center',
        loading ? 'chat-send-button--loading' : disabled ? 'chat-send-button--disabled' : 'chat-send-button--ready',
      ].join(' ')
    "
    :icon-class="loading ? 'h-5 w-5 animate-pulse text-current' : 'h-5 w-5 text-current'"
    @click="loading ? $emit('stop') : $emit('click')"
  />
</template>

<style scoped>
.chat-send-button {
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease !important;
}

.chat-send-button.v-btn--disabled {
  opacity: 1 !important;
}

.chat-send-button :deep(.v-btn__overlay),
.chat-send-button :deep(.v-btn__underlay) {
  opacity: 0 !important;
}

.chat-send-button--ready,
.chat-send-button--loading {
  background: #111827 !important;
  color: #ffffff !important;
}

.chat-send-button--ready:hover {
  background: #1f2937 !important;
  color: #ffffff !important;
}

.chat-send-button--loading:hover {
  background: #111827 !important;
  color: #ffffff !important;
}

.chat-send-button--disabled {
  cursor: not-allowed;
  background: #e5e7eb !important;
  color: #9ca3af !important;
}

.chat-send-button--disabled:hover {
  background: #e5e7eb !important;
  color: #9ca3af !important;
}
</style>
