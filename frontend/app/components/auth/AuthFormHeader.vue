<script setup lang="ts">
defineProps<{
  title: string;
  subtitle: string;
}>();
</script>

<template>
  <img
    src="/logo/gdce-new-seal.png"
    alt=""
    class="mx-auto h-20 w-20 object-contain"
    loading="eager"
    decoding="async"
  />

  <h1 class="mt-8 text-4xl font-normal leading-tight text-white">
    {{ title }}
  </h1>
  <p class="mx-auto mt-3 max-w-[360px] text-lg font-light leading-relaxed text-white/72">
    {{ subtitle }}
  </p>
</template>
