<template>
  <BaseSwitch v-bind="$attrs" :model-value="modelValue" @update:model-value="onUpdate" />
</template>

<script setup lang="ts">
defineProps<{
  modelValue?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

function onUpdate(value: boolean) {
  emit('update:modelValue', value);
}
</script>
