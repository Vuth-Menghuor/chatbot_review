<template>
  <section :data-settings-spy="spyId" class="space-y-3 scroll-mt-20">
    <h3 v-if="title" class="settings-section-title px-1">{{ title }}</h3>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{
  spyId: string;
  title?: string;
}>();
</script>
