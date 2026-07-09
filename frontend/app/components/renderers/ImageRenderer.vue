<script setup lang="ts">
import { toRef } from 'vue';
import type { MessageBlock } from '~/types/message';
import { LucideRefreshCw, LucideDownload } from 'lucide-vue-next';
import { useImageRenderer } from '~/composables/renderers/useImageRenderer';
import ErrorRenderer from './ErrorRenderer.vue';

const props = defineProps<{
  block: MessageBlock;
}>();

const emit = defineEmits<{
  (e: 'regenerate', messageId: string): void;
}>();

const {
  isLoading,
  isError,
  imageUrl,
  prompt,
  hasStructuredApiError,
  errorBlock,
  canUseImageActions,
  onImageLoad,
  onImageError,
  handleDownload,
  handleRegenerate,
  openImage,
} = useImageRenderer(toRef(props, 'block'), (event, id) => emit(event, id));
</script>

<template>
  <div class="w-full max-w-full">
    <!-- Loading Skeleton -->
    <BaseCard
      v-if="isLoading"
      custom-class="image-shell overflow-hidden bg-white dark:bg-zinc-950 image-frame"
    >
      <div class="image-frame relative overflow-hidden rounded-lg">
        <v-skeleton-loader type="image" class="image-skeleton h-full w-full" />
      </div>
    </BaseCard>

    <!-- Error: structured payload from API, or transport failure (no fake copy) -->
    <div v-else-if="isError && hasStructuredApiError" class="image-shell">
      <ErrorRenderer :block="errorBlock" @retry="handleRegenerate" />
    </div>
    <div
      v-else-if="isError"
      class="image-shell rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200"
    >
      {{ $t('image.loadError') }}
    </div>

    <!-- Image -->
    <BaseCard
      v-else
      custom-class="image-shell group relative overflow-hidden rounded-lg bg-white dark:bg-zinc-950 image-frame"
    >
      <v-img
        v-if="imageUrl"
        :src="imageUrl"
        :alt="prompt"
        cover
        @click="openImage"
        @load="onImageLoad"
        @error="onImageError"
      />

      <!-- Hover actions -->
      <div
        v-if="canUseImageActions"
        class="pointer-events-none absolute inset-0 bg-linear-to-b from-black/35 via-transparent to-black/35 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      />
      <div
        v-if="canUseImageActions"
        class="absolute right-3 top-3 flex items-center gap-1.5 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      >
        <BaseIconButton
          :icon="LucideDownload"
          size="small"
          :tooltip="$t('chat.actions.downloadImage')"
          custom-class="bg-black/35 text-white hover:bg-black/50 backdrop-blur !rounded-lg"
          @click="handleDownload"
        />
        <BaseIconButton
          :icon="LucideRefreshCw"
          size="small"
          :tooltip="$t('chat.actions.regenerateImage')"
          custom-class="bg-black/35 text-white hover:bg-black/50 backdrop-blur !rounded-lg"
          @click="handleRegenerate"
        />
      </div>

      <div
        v-if="prompt"
        class="border-t border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400"
      >
        <span class="font-semibold">{{ $t('image.promptLabel') }}:</span>
        {{ prompt }}
      </div>
    </BaseCard>
  </div>
</template>

<style scoped>
.image-shell {
  width: min(100%, 420px);
  margin-inline: 0;
}

.image-shell :deep(.v-card-text) {
  padding: 0 !important;
}

.image-frame {
  height: clamp(220px, 40vw, 450px);
  width: 100%;
}

.image-skeleton,
.image-skeleton :deep(.v-skeleton-loader__bone) {
  height: 100%;
  width: 100%;
}
</style>
