<script setup lang="ts">
import { LucideCheck, LucideCopy } from 'lucide-vue-next';
import {
  stringifyClipboardContent,
  useClipboardCopy,
} from '~/composables/common/useClipboardCopy';

export type BaseCopyVariant = 'icon' | 'box';

interface Props {
  /** `icon` — icon button (renderers). `box` — link field + copy button (share dialog). */
  variant?: BaseCopyVariant;
  content?: string | object;
  value?: string;
  buttonVariant?: 'flat' | 'text' | 'elevated' | 'tonal' | 'outlined' | 'plain';
  color?: string;
  size?: 'x-small' | 'small' | 'default' | 'large' | 'x-large';
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'icon',
  buttonVariant: 'plain',
  color: 'neutral',
  size: 'small',
});

defineOptions({ inheritAttrs: false });

const { copied, copyText } = useClipboardCopy({
  fallbackToTextarea: props.variant === 'box',
});

async function handleCopy() {
  const payload =
    props.variant === 'box' ? props.value : stringifyClipboardContent(props.content ?? '');
  if (!payload) return;
  await copyText(payload);
}
</script>

<template>
  <div v-if="variant === 'box'"
    class="flex items-center gap-0 overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-zinc-700 dark:bg-zinc-900">
    <span class="flex-1 truncate px-4 py-3 font-mono text-sm text-gray-600 select-all dark:text-zinc-300">
      {{ value }}
    </span>
    <BaseButton variant="flat" :color="copied ? 'success' : undefined" :custom-class="[
      'h-auto min-w-[110px] shrink-0 rounded-l-none rounded-r-xl px-2 py-3 text-none font-semibold',
      copied ? '' : '!bg-zinc-900 !text-white',
    ].join(' ')" @click="handleCopy">
      <span v-if="copied" class="flex items-center justify-center gap-1.5">
        <LucideCheck class="h-4 w-4" />
        {{ $t('common.copied') }}
      </span>
      <span v-else>{{ $t('common.copyLink') }}</span>
    </BaseButton>
  </div>

  <BaseIconButton
    v-else
    v-bind="$attrs"
    :icon="copied ? LucideCheck : LucideCopy"
    :variant="buttonVariant"
    :color="color"
    :size="size"
    :tooltip="copied ? $t('common.copied') : $t('common.copyContent')"
    :custom-class="[
      'text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-300',
      copied ? 'scale-110' : '',
    ].join(' ')"
    @click="handleCopy"
  />
</template>
