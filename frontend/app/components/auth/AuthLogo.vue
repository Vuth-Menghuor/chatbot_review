<script setup lang="ts">
import { useAppLocale } from '~/composables/common/useAppLocale';

withDefaults(
  defineProps<{
    class?: string;
  }>(),
  {},
);

const { t } = useAppLocale();
</script>

<template>
  <div :class="['flex justify-center', $props.class]">
    <img
      src="/logo/gdce-new-seal.png"
      :alt="t('auth.logoAlt')"
      class="h-16 w-auto max-w-20 select-none object-contain sm:h-20 sm:max-w-24"
      loading="eager"
      decoding="async"
    />
  </div>
</template>
