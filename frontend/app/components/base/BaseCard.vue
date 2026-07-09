<template>
  <v-card
    v-if="variant !== 'panel'"
    class="overflow-hidden rounded-2xl border border-gray-100 bg-white transition-[border-color,box-shadow,transform] duration-300 dark:border-zinc-800 dark:bg-zinc-950"
    :class="{
      'hover:-translate-y-0.5 hover:border-gray-200 hover:shadow-lg dark:hover:border-zinc-700':
        hover,
    }"
    :elevation="0"
    :color="color"
    v-bind="$attrs"
  >
    <div
      v-if="$slots.header || title"
      class="border-b border-gray-200 px-6 py-4 dark:border-zinc-800"
    >
      <slot name="header">
        <div class="flex items-center justify-between">
          <v-card-title class="text-lg font-bold text-gray-900 dark:text-zinc-100">
            {{ title }}
          </v-card-title>
          <div class="flex items-center gap-1">
            <slot name="header-action" />
            <BaseIconButton v-if="closable" :icon="XIcon" size="small" @click="$emit('close')" />
          </div>
        </div>
      </slot>
    </div>
    <v-card-text :class="padding ? 'p-6' : 'p-0'">
      <slot />
    </v-card-text>

    <div v-if="$slots.footer" class="border-t border-gray-200 px-6 py-4 dark:border-zinc-700">
      <slot name="footer" />
    </div>
  </v-card>

  <div
    v-else
    :class="[
      'overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60',
      padding ? 'p-5' : 'p-0',
      customClass,
    ]"
    v-bind="$attrs"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import { XIcon } from 'lucide-vue-next';

export type BaseCardVariant = 'default' | 'panel';

interface Props {
  variant?: BaseCardVariant;
  title?: string;
  color?: string;
  hover?: boolean;
  padding?: boolean;
  closable?: boolean;
  customClass?: string;
}

defineEmits<{ close: [] }>();

withDefaults(defineProps<Props>(), {
  variant: 'default',
  hover: false,
  padding: true,
  closable: false,
  customClass: '',
});
</script>
