<template>
  <BaseDialog
    v-model="model"
    :title="title"
    :width="width"
    padding="none"
    :content-class="mergedContentClass"
  >
    <section
      class="flex flex-col overflow-hidden bg-white dark:bg-zinc-950"
      :style="shellStyle"
    >
      <div
        class="flex shrink-0 items-center gap-2 border-b border-gray-100 bg-white dark:border-zinc-800 dark:bg-zinc-950"
        :class="headerClass || 'px-4 py-2'"
      >
        <BaseInput
          v-model="query"
          type="search"
          class="min-w-0 flex-1"
          :placeholder="searchPlaceholder"
          :variant="searchVariant"
          :prepend-icon="SearchIcon"
          :append-icon="inputAppendIcon"
          :autofocus="autofocus"
          :aria-label="searchPlaceholder"
          @append-click="onAppendClick"
        />
        <BaseIconButton
          v-if="showCloseIcon"
          :icon="XIcon"
          size="small"
          :tooltip="closeTooltip ?? $t('search.closeDialog')"
          :aria-label="closeTooltip ?? $t('search.closeDialog')"
          custom-class="shrink-0 text-gray-500 hover:text-gray-800 dark:text-zinc-400 dark:hover:text-zinc-100"
          @click="closeDialog"
        />
      </div>
      <v-divider v-if="showDivider" class="shrink-0 opacity-10" />
      <div
        class="custom-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain"
        :class="bodyClass"
      >
        <slot :query="query" />
      </div>
    </section>
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { SearchIcon, XIcon } from 'lucide-vue-next';
import type { Component } from 'vue';

const props = withDefaults(
  defineProps<{
    title?: string;
    width?: number | string;
    /** Fixed shell height (header + scrollable body). */
    maxHeight?: string;
    searchPlaceholder: string;
    searchVariant?: 'default' | 'plain';
    contentClass?: string;
    headerClass?: string;
    bodyClass?: string;
    showDivider?: boolean;
    autofocus?: boolean;
    showCloseIcon?: boolean;
    appendMode?: 'close' | 'clear';
    closeTooltip?: string;
    appendIcon?: Component;
  }>(),
  {
    width: 640,
    maxHeight: '50vh',
    searchVariant: 'plain',
    contentClass: '',
    bodyClass: 'px-2 py-2',
    showDivider: true,
    autofocus: true,
    showCloseIcon: true,
    appendMode: 'close',
  },
);

const model = defineModel<boolean>({ required: true });
const query = defineModel<string>('query', { default: '' });

const mergedContentClass = computed(
  () => `overflow-hidden p-0 ${props.contentClass}`.trim(),
);

const shellStyle = computed(() => ({
  height: props.maxHeight,
  maxHeight: props.maxHeight,
}));

const inputAppendIcon = computed(() => {
  if (props.showCloseIcon) {
    return undefined;
  }
  if (props.appendMode === 'close') {
    return XIcon;
  }
  return query.value ? XIcon : props.appendIcon;
});

function closeDialog() {
  model.value = false;
}

function onAppendClick() {
  if (props.appendMode === 'close') {
    closeDialog();
    return;
  }
  query.value = '';
}
</script>
