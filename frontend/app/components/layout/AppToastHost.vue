<template>
  <div
    class="pointer-events-none fixed right-4 top-4 z-200 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2"
  >
    <TransitionGroup name="toast">
      <div
        v-for="toast in notificationStore.toasts"
        :key="toast.id"
        class="pointer-events-auto overflow-hidden rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-xl shadow-gray-900/10 dark:border-zinc-800 dark:bg-zinc-950 dark:shadow-black/30"
      >
        <div class="flex items-start gap-3">
          <div
            class="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full"
            :class="toast.type === 'success' ? 'bg-emerald-500' : 'bg-blue-500'"
          />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-gray-950 dark:text-zinc-100">{{ toast.title }}</p>
            <p v-if="toast.message" class="mt-0.5 text-sm text-gray-500 dark:text-zinc-400">
              {{ toast.message }}
            </p>
          </div>
          <BaseIconButton
            :icon="XIcon"
            size="x-small"
            :tooltip="$t('toast.dismiss')"
            custom-class="-mr-1 text-gray-400 hover:text-gray-700 dark:text-zinc-500 dark:hover:text-zinc-200"
            @click="notificationStore.removeToast(toast.id)"
          />
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { XIcon } from 'lucide-vue-next';
import { useNotificationStore } from '~/stores/notification.store';

const notificationStore = useNotificationStore();
</script>
