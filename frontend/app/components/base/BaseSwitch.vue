<template>
  <button
    type="button"
    role="switch"
    class="base-switch inline-flex shrink-0 items-center rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50 dark:focus-visible:ring-offset-zinc-950"
    :class="[sizeClass, trackClass]"
    :aria-checked="isOn"
    :aria-label="ariaLabel"
    :disabled="disabled"
    @click="toggle"
  >
    <span
      class="base-switch-thumb block rounded-full bg-white shadow-sm transition-transform duration-200"
      :class="thumbClass"
    />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue';

type SwitchSize = 'sm' | 'md';

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    disabled?: boolean;
    ariaLabel?: string;
    size?: SwitchSize;
  }>(),
  {
    modelValue: false,
    disabled: false,
    size: 'md',
  },
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const isOn = computed(() => !!props.modelValue);

const sizeClass = computed(() =>
  props.size === 'sm' ? 'h-5 w-9' : 'h-6 w-11',
);

const thumbClass = computed(() => {
  const size = props.size === 'sm' ? 'h-4 w-4' : 'h-5 w-5';
  const offset = props.size === 'sm' ? 'translate-x-4' : 'translate-x-5';
  return [size, isOn.value ? offset : 'translate-x-0.5'];
});

const trackClass = computed(() =>
  isOn.value ? 'bg-primary' : 'bg-gray-200 dark:bg-zinc-700',
);

function toggle() {
  if (props.disabled) return;
  emit('update:modelValue', !isOn.value);
}
</script>
