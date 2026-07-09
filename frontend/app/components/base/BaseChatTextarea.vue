<template>
  <v-textarea
    v-bind="$attrs"
    :model-value="modelValue"
    variant="plain"
    auto-grow
    :rows="rows"
    :max-rows="maxRows"
    hide-details
    density="compact"
    :class="[
      'flex-1 text-base [&_textarea]:resize-none [&_textarea]:text-gray-900 dark:[&_textarea]:text-zinc-100',
      '[&_textarea::placeholder]:text-gray-400 dark:[&_textarea::placeholder]:text-zinc-500',
      customClass,
    ]"
    @update:model-value="$emit('update:modelValue', $event)"
    @keydown="$emit('keydown', $event)"
  />
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue?: string;
    rows?: number | string;
    maxRows?: number | string;
    customClass?: string;
  }>(),
  {
    modelValue: '',
    rows: 1,
    maxRows: 8,
    customClass: '',
  },
);

defineEmits<{
  'update:modelValue': [value: string];
  keydown: [event: KeyboardEvent];
}>();
</script>
