<template>
  <div class="settings-row">
    <div class="settings-label">{{ label }}</div>
    <div class="settings-control">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
}>();
</script>
