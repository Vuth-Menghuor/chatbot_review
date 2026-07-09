<script setup lang="ts">
import type { MessageBlock } from '~/types/message';
import { useErrorRenderer } from '~/composables/renderers/useErrorRenderer';

const props = defineProps<{ block: MessageBlock }>();

const emit = defineEmits<{
  (e: 'retry'): void;
}>();

const { t } = useI18n();
const { headline, body, technicalHint, retryable, retryLabel, friendlyDisplay } =
  useErrorRenderer(props.block);
</script>

<template>
  <div class="error-renderer-wrap w-full">
    <BaseFriendlyErrorPanel
      class="error-renderer-block"
      :title="headline"
      :message="body"
      :technical-details="technicalHint || undefined"
      :technical-details-label="t('error.technicalDetails')"
      :technical-details-hide-label="t('error.hideDetails')"
      :retryable="retryable"
      :retry-label="retryLabel"
      :shell-class="friendlyDisplay.shellClass.value"
      :icon-wrap-class="friendlyDisplay.iconWrapClass.value"
      :icon-component="friendlyDisplay.iconComponent.value"
      @retry="emit('retry')"
    />
  </div>
</template>
