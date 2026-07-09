<template>
  <div
    :class="
      docked
        ? 'sticky bottom-0 z-30 w-full shrink-0 bg-linear-to-t from-white from-50% via-white/95 to-transparent px-3 pb-[max(8px,env(safe-area-inset-bottom))] pt-4 dark:from-zinc-950 dark:via-zinc-950/95 md:px-4'
        : ''
    "
  >
    <div :class="docked ? 'mx-auto w-full max-w-3xl' : ''">
      <div
        class="rounded-4xl border border-gray-300 bg-white p-2 shadow-sm transition-all duration-300 focus-within:shadow-md dark:border-zinc-700 dark:bg-zinc-900 dark:shadow-none dark:focus-within:shadow-[0_0_0_1px_rgba(255,255,255,0.08)]"
      >    <!-- File Preview -->
    <CommonFilePreview :files="attachedFiles" @remove="removeFile" />

    <!-- Hidden File Input (Using Vuetify v-file-input) -->
    <v-file-input
      ref="fileInputRef"
      multiple
      class="hidden"
      :accept="imageAccept"
      @update:model-value="onFileChange"
    />

    <!-- Main Container -->
    <div class="flex flex-col">
      <!-- Row 1: Plus (Inline) + Textarea + Send (Inline) -->
      <div class="flex items-center">
        <BaseIconButton
          v-if="!isMultiLine"
          :icon="PlusIcon"
          size="large"
          width="44"
          height="44"
          :custom-class="plusButtonClass"
          @click="fileInputRef?.click()"
        />

        <BaseChatTextarea
          id="chat-input-textarea"
          ref="textareaRef"
          v-model="model"
          :placeholder="$t('chat.placeholder')"
          aria-label="chat-input-textarea"
          custom-class="chat-input-textarea flex-1 pt-2 px-2 ml-1"
          @keydown="onKeydown"
        />

        <CommonSendButton
          v-if="!isMultiLine"
          :disabled="!canSend"
          :loading="loading"
          @click="submit"
          @stop="$emit('stop')"
        />
      </div>

      <!-- Row 2: Bottom Toolbar (MultiLine only) -->
      <div v-if="isMultiLine" class="flex items-center justify-between p-1">
        <BaseIconButton
          :icon="PlusIcon"
          size="large"
          width="44"
          height="44"
          :custom-class="plusButtonClass"
          @click="fileInputRef?.click()"
        />

        <CommonSendButton
          :disabled="!canSend"
          :loading="loading"
          @click="submit"
          @stop="$emit('stop')"
        />
      </div>
    </div>
    </div>

      <p
        v-if="docked"
        class="px-2 pt-2 text-center text-[10px] leading-tight text-gray-400 dark:text-zinc-500 md:text-[11px]"
      >
        {{ $t('chat.disclaimer') }}
      </p>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, nextTick } from 'vue';
import { PlusIcon } from 'lucide-vue-next';
import BaseIconButton from '~/components/base/BaseIconButton.vue';
import { usePreferencesStore } from '~/stores/preferences.store';
import { useNotificationStore } from '~/stores/notification.store';
import { getImageUploadLimits, imageAcceptAttribute, validateImageFile } from '~/utils/file/imageUpload';

const plusButtonClass =
  'text-gray-600 bg-gray-100 hover:!bg-gray-200 !rounded-full dark:bg-zinc-800 dark:text-zinc-300 dark:hover:!bg-zinc-700';

const preferencesStore = usePreferencesStore();
const notificationStore = useNotificationStore();
const runtimeConfig = useRuntimeConfig();
const imageLimits = computed(() =>
  getImageUploadLimits(
    runtimeConfig.public.allowedImageTypes as string | string[],
    runtimeConfig.public.maxImageSizeMb as number | string,
  ),
);
const imageAccept = computed(() => imageAcceptAttribute(imageLimits.value));
const model = ref('');
const attachedFiles = ref<File[]>([]);

// Detect if there are multiple lines (ChatGPT style: moves buttons to bottom row)
const isMultiLine = computed(() => {
  // We consider it multiline if there's a newline character or if text is very long
  // Also if there are any attached files, we use the expanded toolbar layout
  return model.value.includes('\n') || model.value.length > 60 || attachedFiles.value.length > 0;
});

const canSend = computed(() => model.value.trim().length > 0 || attachedFiles.value.length > 0);

const fileInputRef = ref<InstanceType<typeof import('vuetify/components').VFileInput> | null>(null);
const textareaRef = ref<InstanceType<typeof import('vuetify/components').VTextarea> | null>(null);

const onFileChange = (files: File | File[] | File[] | null) => {
  if (!files) return;
  const filesArray = Array.isArray(files) ? files : [files];
  for (const file of filesArray) {
    const error = validateImageFile(file, imageLimits.value);
    if (error) {
      notificationStore.showToast({ type: 'error', title: 'Invalid file', message: error });
      continue;
    }
    attachedFiles.value.push(file);
  }
};

const onKeydown = (e: KeyboardEvent) => {
  if (e.key !== 'Enter' || e.shiftKey) return;

  if (preferencesStore.enterToSend) {
    e.preventDefault();
    submit();
    return;
  }

  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    submit();
  }
};

const props = withDefaults(
  defineProps<{
    loading?: boolean;
    /** Bottom dock layout with centered width and disclaimer (home + chat pages). */
    docked?: boolean;
  }>(),
  {
    docked: true,
  },
);

const emit = defineEmits<{
  (
    e: 'send',
    payload: { text: string; files: File[]; onResult?: (accepted: boolean) => void },
  ): void;
  (e: 'stop'): void;
}>();

const submit = () => {
  if (canSend.value && !props.loading) {
    const text = model.value;
    const files = [...attachedFiles.value];
    model.value = '';
    attachedFiles.value = [];
    emit('send', {
      text,
      files,
      onResult: (accepted) => {
        if (!accepted) {
          model.value = text;
          attachedFiles.value = files;
        }
      },
    });
  }
};
const removeFile = (index: number) => attachedFiles.value.splice(index, 1);

const focusTextarea = async () => {
  await nextTick();
  const textarea = textareaRef.value?.$el?.querySelector('textarea') as HTMLTextAreaElement | null;
  textarea?.focus();
  if (textarea) {
    const end = textarea.value.length;
    textarea.setSelectionRange(end, end);
  }
};

const setDraft = async (text: string) => {
  model.value = text;
  await focusTextarea();
};

defineExpose({ setDraft });
</script>

<style scoped>
:deep(.chat-send-button--ready),
:deep(.chat-send-button--loading) {
  background: #111827 !important;
  color: #ffffff !important;
}

:deep(.chat-send-button--ready:hover),
:deep(.chat-send-button--loading:hover) {
  background: #1f2937 !important;
}

:deep(.chat-send-button--disabled),
:deep(.chat-send-button--disabled:hover) {
  background: #e5e7eb !important;
  color: #9ca3af !important;
}

html.dark :deep(.chat-send-button--ready),
html.dark :deep(.chat-send-button--loading),
html.dark :deep(.chat-send-button--ready:hover),
html.dark :deep(.chat-send-button--loading:hover) {
  background: #f4f4f5 !important;
  color: #18181b !important;
}

html.dark :deep(.chat-send-button--disabled),
html.dark :deep(.chat-send-button--disabled:hover) {
  background: #3f3f46 !important;
  color: #71717a !important;
}
</style>