<script setup lang="ts">
import type { Component } from 'vue';
import type { TooltipLocation } from '~/types/message';

interface Props {
  variant?: 'flat' | 'text' | 'elevated' | 'tonal' | 'outlined' | 'plain';
  color?: string;
  size?: 'x-small' | 'small' | 'default' | 'large' | 'x-large';
  tooltip?: string;
  tooltipLocation?: TooltipLocation;
  loading?: boolean;
  disabled?: boolean;
  rounded?: boolean;
  square?: boolean;
  block?: boolean;
  /** Pushes prepend/append to the edges (Vuetify 4 `spaced`). */
  spaced?: 'start' | 'end' | 'both';
  justify?: 'start' | 'center' | 'end';
  prependIcon?: Component;
  appendIcon?: Component;
  customClass?: string;
}

withDefaults(defineProps<Props>(), {
  variant: 'flat',
  size: 'default',
  rounded: true,
  justify: 'center',
  tooltipLocation: 'bottom',
});
</script>
  
<template>
  <v-btn
    :block="block && !square"
    :spaced="spaced"
    :class="[
      'text-none font-medium transition-all duration-200 px-2',
      variant === 'flat' && !color ? 'text-white bg-zinc-800' : '',
      rounded && !square ? 'rounded-lg' : 'rounded-lg',
      square ? 'w-10 h-10 min-w-0 p-0' : '',
      block && !square ? 'w-full' : '',
      justify === 'start' ? 'justify-start' : justify === 'center' ? 'justify-center' : '',
      customClass,
    ]"
    :variant="variant"
    :color="color"
    :size="size"
    :loading="loading"
    :disabled="disabled"
    v-bind="$attrs"
  >
    <template v-if="prependIcon || $slots.prepend" #prepend>
      <slot name="prepend">
        <component
          :is="prependIcon"
          class="lucide w-5 h-5 shrink-0 text-current"
          :class="{ 'mr-2': $slots.default }"
        />
      </slot>
    </template>

    <slot />

    <template v-if="appendIcon || $slots.append" #append>
      <slot name="append">
        <component
          :is="appendIcon"
          class="lucide w-5 h-5 shrink-0 text-current"
          :class="{ 'ml-2': $slots.default }"
        />
      </slot>
    </template>

    <BaseTooltip v-if="tooltip" :text="tooltip" :location="tooltipLocation" />
  </v-btn>
</template>
