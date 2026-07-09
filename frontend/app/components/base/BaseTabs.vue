<template>
  <div class="flex w-full flex-col">
    <div
      :class="[
        variant === 'pill'
          ? 'mb-4 flex items-center gap-1 self-start rounded-xl bg-gray-100 p-1 dark:bg-zinc-800'
          : 'flex items-center gap-4 self-start',
      ]"
    >
      <button
        v-for="tab in items"
        :key="tab.value"
        type="button"
        :class="[
          variant === 'pill'
            ? 'rounded-lg px-4 py-1.5 text-base font-medium transition-colors duration-200'
            : 'relative px-0 pb-3 text-sm font-semibold transition-colors duration-200',

          variant === 'pill' && model === tab.value
            ? 'bg-white text-gray-900 shadow-sm dark:bg-zinc-700 dark:text-zinc-100'
            : '',

          variant === 'pill' && model !== tab.value
            ? 'text-gray-500 hover:text-gray-700 dark:text-zinc-400 dark:hover:text-zinc-300'
            : '',

          variant === 'underline' && model === tab.value
            ? 'text-orange-600 dark:text-orange-400'
            : '',

          variant === 'underline' && model !== tab.value
            ? 'text-gray-500 hover:text-gray-800 dark:text-zinc-400 dark:hover:text-zinc-200'
            : '',
        ]"
        @click="model = tab.value"
      >
        <div class="flex items-center gap-2">
          <component :is="tab.icon" v-if="tab.icon" class="h-4 w-4" />
          {{ tab.title }}
        </div>

        <span
          v-if="variant === 'underline' && model === tab.value"
          class="absolute inset-x-0 bottom-0 h-[3px] rounded-t bg-orange-500 dark:bg-orange-400"
        />
      </button>
    </div>

    <slot :name="model" />
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue';

interface TabItem {
  title: string;
  value: string;
  icon?: Component;
}

interface Props {
  items: TabItem[];
  variant?: 'pill' | 'underline';
}

const model = defineModel<string>();

withDefaults(defineProps<Props>(), {
  variant: 'pill',
});
</script>
