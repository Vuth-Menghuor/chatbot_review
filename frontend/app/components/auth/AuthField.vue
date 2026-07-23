<script setup lang="ts">
import { computed, ref } from 'vue';
import { EyeIcon, EyeOffIcon } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    label: string;
    placeholder?: string;
    type?: string;
    autocomplete?: string;
    password?: boolean;
  }>(),
  {
    type: 'text',
    placeholder: '',
    autocomplete: undefined,
    password: false,
  },
);

const model = defineModel<string>({ default: '' });
const showPassword = ref(false);
const inputType = computed(() => (props.password && !showPassword.value ? 'password' : props.type));
</script>

<template>
  <fieldset
    class="rounded-sm border border-white/65 bg-transparent px-4 pb-3 pt-1 focus-within:border-white/95"
  >
    <legend class="px-2 text-sm font-medium uppercase text-white/70">
      {{ label }}
    </legend>
    <div class="flex items-center gap-3">
      <input
        v-model="model"
        :type="inputType"
        :autocomplete="autocomplete"
        :placeholder="placeholder"
        class="min-w-0 flex-1 bg-transparent text-base text-white/95 outline-none placeholder:text-white/55"
      />
      <button
        v-if="password"
        type="button"
        class="flex h-7 w-7 items-center justify-center text-white transition hover:text-white"
        :aria-label="showPassword ? 'Hide password' : 'Show password'"
        @click="showPassword = !showPassword"
      >
        <component
          :is="showPassword ? EyeOffIcon : EyeIcon"
          class="h-4 w-4 text-white opacity-90"
          stroke-width="2.25"
        />
      </button>
    </div>
  </fieldset>
</template>
