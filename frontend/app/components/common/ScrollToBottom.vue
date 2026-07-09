<script setup lang="ts">
import { ArrowDownIcon } from 'lucide-vue-next';

defineProps<{
  show: boolean;
  loading?: boolean;
}>();

defineEmits<{
  (e: 'click'): void;
}>();
</script>

<template>
  <Transition name="fade">
    <div v-if="show" class="pointer-events-none flex justify-center pb-2">
      <BaseIconButton :icon="loading ? undefined : ArrowDownIcon" size="x-small" variant="flat"
        custom-class="pointer-events-auto min-w-0 !rounded-full border border-gray-200/70 bg-surface text-gray-600 shadow-md backdrop-blur-md transition-colors hover:bg-white/95 dark:border-zinc-700/70 dark:bg-zinc-900/80 dark:text-zinc-300 dark:hover:bg-zinc-900/95"
        :class="loading ? 'h-9 w-11' : 'h-9 w-9'" icon-class="h-5 w-5" @click="$emit('click')">
        <div v-if="loading" class="flex items-center justify-center space-x-0.5">
          <span class="dot" />
          <span class="dot" />
          <span class="dot" />
        </div>
      </BaseIconButton>
    </div>
  </Transition>
</template>

<style scoped>
.dot {
  width: 4px;
  height: 4px;
  background-color: currentColor;
  border-radius: 50%;
  animation: dot-pulse 1.4s infinite ease-in-out both;
}

.dot:nth-child(1) {
  animation-delay: -0.32s;
}

.dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes dot-pulse {

  0%,
  80%,
  100% {
    transform: scale(0);
    opacity: 0.3;
  }

  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
