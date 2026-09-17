<template>
  <span
    v-if="decorative"
    role="img"
    :aria-hidden="ariaHidden"
    :class="['inline-flex shrink-0 items-center justify-center', customClass]"
  >
    <component
      :is="icon"
      v-if="icon"
      :class="[iconSizeClass, iconClass ?? 'text-high-emphasis']"
    />
    <slot />
  </span>

  <v-btn
    v-else
    icon
    :class="[
      'rounded-lg transition-colors duration-200',
      variant === 'text'
        ? 'text-gray-700 hover:bg-gray-200/50 hover:text-gray-800 dark:text-zinc-200 dark:hover:bg-zinc-800 dark:hover:text-zinc-100'
        : '',
      customClass,
    ]"
    :variant="variant"
    :color="color"
    :size="size"
    :loading="loading"
    :disabled="disabled"
    v-bind="$attrs"
  >
    <component
      :is="icon"
      v-if="icon"
      :class="[iconSizeClass, iconClass ?? 'text-current']"
    />
    <slot />

    <BaseTooltip v-if="tooltip" :text="tooltip" :location="tooltipLocation" />
  </v-btn>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue';
import type { TooltipLocation } from '~/types/message';

interface Props {
  icon?: Component;
  variant?: 'flat' | 'text' | 'elevated' | 'tonal' | 'outlined' | 'plain';
  color?: string;
  size?: 'x-small' | 'small' | 'default' | 'large' | 'x-large';
  loading?: boolean;
  disabled?: boolean;
  tooltip?: string;
  tooltipLocation?: TooltipLocation;
  customClass?: string;
  iconClass?: string;
  /** Non-interactive icon display (list leading icons, etc.). */
  decorative?: boolean;
  ariaHidden?: boolean | 'true' | 'false';
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'text',
  size: 'default',
  tooltipLocation: 'bottom',
  decorative: false,
  ariaHidden: true,
});

const iconSizeClass = computed(() => {
  switch (props.size) {
    case 'x-small':
      return 'w-4 h-4';
    case 'small':
      return 'w-5 h-5';
    case 'large':
      return 'w-6 h-6';
    default:
      return 'w-5 h-5';
  }
});
</script>
