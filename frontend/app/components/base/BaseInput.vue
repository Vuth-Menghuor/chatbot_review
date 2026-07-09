<template>
  <div class="flex w-full flex-col" :class="variant === 'auth' ? 'gap-1.5' : 'gap-2'">
    <label
      v-if="label"
      class="text-gray-700 dark:text-zinc-300"
      :class="[
        variant === 'auth' ? 'ml-0 text-sm font-semibold text-[#3d4f59]' : 'ml-2 text-base',
        boldLabel && variant !== 'auth' ? 'font-semibold text-gray-900 dark:text-zinc-100' : '',
      ]"
    >
      {{ label }}
    </label>

    <div class="relative group">
      <div
        v-if="prependIcon"
        class="lucide pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors dark:text-zinc-500"
      >
        <component :is="prependIcon" :class="[size === 'lg' ? 'w-5 h-5' : 'w-[18px] h-[18px]']" />
      </div>

      <textarea
        v-if="type === 'textarea'"
        v-model="model"
        v-bind="$attrs"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        class="w-full resize-none font-normal outline-none transition-colors duration-200 disabled:opacity-50 dark:text-zinc-100"
        :class="[
          variant === 'default' || variant === 'auth'
            ? defaultFieldClass
            : 'bg-transparent border-0 py-3 px-1',
          error && (variant === 'default' || variant === 'auth')
            ? noFocusRing
              ? 'border-red-500 focus:border-red-500'
              : 'border-red-500 focus:ring-red-500/20 focus:border-red-500'
            : '',
        ]"
        :rows="textareaRows"
      ></textarea>

      <input
        v-else
        v-model="model"
        v-bind="$attrs"
        :type="type"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        class="w-full font-normal outline-none transition-colors duration-200 disabled:opacity-50 dark:text-zinc-100"
        :class="[
          variant === 'default' || variant === 'auth'
            ? defaultFieldClass
            : 'bg-transparent border-0 py-3 px-1',
          prependIcon ? (variant === 'plain' ? 'pl-12' : 'pl-10') : '',
          appendIcon ? 'pr-10' : '',
          error && (variant === 'default' || variant === 'auth')
            ? noFocusRing
              ? 'border-red-500 focus:border-red-500'
              : 'border-red-500 focus:ring-red-500/20 focus:border-red-500'
            : '',
        ]"
      />

      <div
        v-if="appendIcon"
        class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors dark:text-zinc-500"
      >
        <component
          :is="appendIcon"
          :class="[size === 'lg' ? 'w-5 h-5' : 'w-[18px] h-[18px]']"
          class="lucide cursor-pointer text-current"
          @click="$emit('append-click')"
        />
      </div>
    </div>

    <p v-if="error && typeof error === 'string'" class="ml-1 mt-0.5 text-xs text-red-500">
      {{ error }}
    </p>
    <p v-else-if="hint" class="ml-1 mt-0.5 text-xs text-gray-400 dark:text-zinc-500">
      {{ hint }}
    </p>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue';
import { computed } from 'vue';

interface Props {
  label?: string;
  placeholder?: string;
  type?: string;
  variant?: 'default' | 'plain' | 'auth';
  size?: 'md' | 'lg';
  error?: string | boolean;
  hint?: string;
  disabled?: boolean;
  readonly?: boolean;
  prependIcon?: Component;
  appendIcon?: Component;
  textareaRows?: number | string;
  /** When true, focus shows border only — no orange focus ring. */
  noFocusRing?: boolean;
  boldLabel?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  variant: 'default',
  size: 'md',
  textareaRows: 4,
  noFocusRing: false,
  boldLabel: false,
});

const model = defineModel<string | number>();

const defaultFieldClass = computed(() => {
  if (props.variant === 'auth') {
    return 'rounded-sm border border-[#b8c5ce] bg-[#f3f7f9] px-3.5 py-2.5 text-md leading-normal text-black placeholder:text-md placeholder:text-gray-500 focus:border-[#1b5875] focus:bg-white focus:ring-0';
  }
  if (props.noFocusRing) {
    return 'rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm focus:border-gray-400 focus:ring-0 dark:border-zinc-700 dark:bg-zinc-950/60 dark:focus:border-zinc-500';
  }
  return 'rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500/15 dark:border-zinc-700 dark:bg-zinc-950/60';
});

defineEmits<{
  (e: 'append-click'): void;
}>();
</script>
