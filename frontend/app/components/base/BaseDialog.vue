<script setup lang="ts">
import { watch } from 'vue';

interface Props {
  title?: string;
  width?: string | number;
  fullscreen?: boolean;
  padding?: 'default' | 'none';
  contentClass?: string;
  onClose?: () => void;
}

const CLOSE_CALLBACK_DELAY_MS = 300;

const model = defineModel<boolean>();
const props = withDefaults(defineProps<Props>(), {
  width: 500,
  fullscreen: false,
  padding: 'default',
  contentClass: '',
});

const close = () => {
  model.value = false;
};

watch(
  () => model.value,
  (value) => {
    if (!value && props.onClose) {
      setTimeout(() => {
        props.onClose?.();
      }, CLOSE_CALLBACK_DELAY_MS);
    }
  },
);

defineExpose({
  close,
});
</script>

<template>
  <v-dialog
    v-model="model"
    :max-width="width"
    :fullscreen="fullscreen"
    persistent
    transition="dialog-bottom-transition"
    class="settings-dialog overflow-hidden"
  >
    <BaseCard :title="title" :padding="false" closable @close="close">
      <div
        :class="[
          padding === 'default'
            ? 'custom-scrollbar max-h-[80vh] overflow-y-auto bg-white px-6 py-6 dark:bg-zinc-950'
            : '',
          contentClass,
        ]"
      >
        <slot />
      </div>

      <template v-if="$slots.actions" #footer>
        <div class="flex items-center justify-end gap-3">
          <slot name="actions" />
        </div>
      </template>
    </BaseCard>
  </v-dialog>
</template>
