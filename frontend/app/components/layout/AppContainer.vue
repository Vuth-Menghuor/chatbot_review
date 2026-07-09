<template>
  <div
    class="mx-auto w-full px-4 md:px-6 lg:px-8"
    :class="[sizeClass, centered ? 'flex flex-col items-center' : '']"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  centered?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  centered: false,
});

const sizeClass = computed(
  () =>
    ({
      sm: 'max-w-2xl',
      md: 'max-w-4xl',
      lg: 'max-w-5xl',
      xl: 'max-w-7xl',
      full: 'max-w-full',
    })[props.size],
);
</script>
