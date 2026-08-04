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
        class="rounded-[24px] border border-gray-300 bg-white px-4 py-3 dark:border-zinc-700 dark:bg-[#181818]"
      >
        <!-- File Preview -->
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
        <div class="flex min-h-[60px] flex-col justify-between gap-2">
          <!-- Row 1: Textarea -->
          <div class="flex items-start">
            <BaseChatTextarea
              id="chat-input-textarea"
              ref="textareaRef"
              v-model="model"
              :placeholder="$t('chat.placeholder')"
              aria-label="chat-input-textarea"
              custom-class="chat-input-textarea flex-1 px-0 pt-0"
              @keydown="onKeydown"
            />
          </div>

          <!-- Row 2: Bottom Toolbar -->
          <div class="flex items-center justify-between">
            <BaseIconButton
              :icon="PlusIcon"
              size="large"
              width="32"
              height="32"
              :custom-class="plusButtonClass"
              @click="fileInputRef?.click()"
            />

            <div class="flex items-center gap-2">
              <CommonSendButton
                :disabled="!canSend"
                :loading="loading"
                @click="submit"
                @stop="$emit('stop')"
              />
            </div>
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
import { ref, computed, nextTick, onMounted, watch } from 'vue';
import { PlusIcon } from 'lucide-vue-next';
import BaseIconButton from '~/components/base/BaseIconButton.vue';
import { usePreferencesStore } from '~/stores/preferences.store';
import { useNotificationStore } from '~/stores/notification.store';
import {
  getImageUploadLimits,
  imageAcceptAttribute,
  validateImageFile,
} from '~/utils/file/imageUpload';

const plusButtonClass = 'chat-plus-button text-gray-500 !rounded-full dark:text-zinc-300';

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

const canSend = computed(() => model.value.trim().length > 0 || attachedFiles.value.length > 0);

const fileInputRef = ref<InstanceType<typeof import('vuetify/components').VFileInput> | null>(null);
const textareaRef = ref<InstanceType<typeof import('vuetify/components').VTextarea> | null>(null);
const MAX_TEXTAREA_HEIGHT = 220;

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

const resizeTextarea = async () => {
  await nextTick();
  requestAnimationFrame(() => {
    const textarea = textareaRef.value?.$el?.querySelector('textarea') as HTMLTextAreaElement | null;
    if (!textarea) return;

    textarea.style.height = 'auto';
    const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden';

    const fieldInput = textarea.closest('.v-field__input') as HTMLElement | null;
    if (fieldInput) {
      fieldInput.style.height = `${nextHeight + 4}px`;
      fieldInput.style.maxHeight = `${MAX_TEXTAREA_HEIGHT + 4}px`;
      fieldInput.style.overflowY = 'visible';
    }
  });
};

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
  await resizeTextarea();
};

watch(model, () => {
  void resizeTextarea();
});

onMounted(() => {
  void resizeTextarea();
});

defineExpose({ setDraft });
</script>

<style scoped>
:deep(.chat-input-textarea .v-field__input:not(.v-textarea__sizer)) {
  min-height: 32px !important;
  max-height: 224px !important;
  padding: 4px 0 0 !important;
  overflow-y: visible !important;
}

:deep(.chat-input-textarea .v-textarea__sizer) {
  min-height: 32px !important;
  padding: 4px 0 0 !important;
}

:deep(.chat-input-textarea textarea) {
  line-height: 1.45 !important;
  max-height: 220px !important;
  overflow-y: hidden !important;
}

:deep(.chat-input-textarea textarea::placeholder) {
  color: #9ca3af !important;
}

html.dark :deep(.chat-input-textarea textarea::placeholder) {
  color: #8a8a8a !important;
}

:deep(.chat-plus-button),
:deep(.chat-plus-button:hover) {
  background: transparent !important;
  color: #6b7280 !important;
}

html.dark :deep(.chat-plus-button),
html.dark :deep(.chat-plus-button:hover) {
  background: transparent !important;
  color: #d4d4d8 !important;
}

:deep(.chat-plus-button .v-btn__overlay),
:deep(.chat-plus-button .v-btn__underlay) {
  opacity: 0 !important;
}

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
:deep(.chat-send-button--disabled:hover),
:deep(.chat-send-button.v-btn--disabled.chat-send-button--disabled),
:deep(.chat-send-button.v-btn--disabled.chat-send-button--disabled:hover) {
  background: #e5e7eb !important;
  color: #9ca3af !important;
}

html.dark :deep(.chat-send-button--ready),
html.dark :deep(.chat-send-button--loading),
html.dark :deep(.chat-send-button--ready:hover),
html.dark :deep(.chat-send-button--loading:hover) {
  background: #ffffff !important;
  color: #18181b !important;
}

html.dark :deep(.chat-send-button--disabled),
html.dark :deep(.chat-send-button--disabled:hover),
html.dark :deep(.chat-send-button.v-btn--disabled.chat-send-button--disabled),
html.dark :deep(.chat-send-button.v-btn--disabled.chat-send-button--disabled:hover) {
  background: #ffffff !important;
  color: #18181b !important;
}
</style>
