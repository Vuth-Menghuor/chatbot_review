<template>
  <component
    :is="as"
    class="rounded-md border border-neutral-200 bg-neutral-100/50 dark:border-neutral-800 dark:bg-neutral-900/40"
    :class="customClass"
  >
    <slot />
  </component>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    as?: string;
    customClass?: string;
  }>(),
  {
    as: 'div',
    customClass: '',
  },
);
</script>
