<script setup lang="ts">
import { computed } from 'vue';
import { CheckIcon } from 'lucide-vue-next';
import { useAppLocale } from '~/composables/common/useAppLocale';

const props = withDefaults(
  defineProps<{
    error?: string;
    compact?: boolean;
    small?: boolean;
  }>(),
  {
    compact: false,
    small: true,
  },
);

const accepted = defineModel<boolean>({ required: true });
const dialogOpen = defineModel<boolean>('dialogOpen', { default: false });

const { t } = useAppLocale();

const bodyKeys = ['p1', 'p2', 'p3', 'p4'] as const;

const hasError = computed(() => Boolean(props.error?.trim()));

const labelClass = computed(() =>
  props.small
    ? 'text-sm leading-normal text-[#4a5d68]'
    : 'text-md leading-normal text-[#4a5d68]',
);

const linkButtonClass = computed(() =>
  [
    'inline font-bold text-[#1b5875] underline-offset-2 hover:underline',
    props.small ? 'text-sm' : 'text-md',
  ].join(' '),
);

const checkboxClass = computed(() => [
  'flex shrink-0 items-center justify-center rounded border bg-white transition-colors',
  'peer-checked:border-[#1b5875] peer-checked:bg-[#1b5875]',
  'peer-focus-visible:ring-2 peer-focus-visible:ring-[#1b5875]/20',
  props.small ? 'h-4 w-4' : 'h-5 w-5',
  hasError.value ? 'border-red-500' : 'border-[#b8c5ce]',
]);

const checkIconClass = computed(() =>
  props.small ? 'h-2.5 w-2.5 text-white' : 'h-3 w-3 text-white',
);

function acceptTerms() {
  accepted.value = true;
  dialogOpen.value = false;
}

function openTerms() {
  dialogOpen.value = true;
}
</script>

<template>
  <div :class="compact ? 'py-0' : 'py-0.5'">
    <label class="flex cursor-pointer items-center gap-2.5 select-none">
      <input
        v-model="accepted"
        type="checkbox"
        class="peer sr-only"
        :aria-invalid="hasError || undefined"
      />

      <span :class="checkboxClass" aria-hidden="true">
        <CheckIcon v-if="accepted" :class="checkIconClass" :stroke-width="3" />
      </span>

      <span :class="[labelClass, 'min-w-0']">
        {{ t('auth.terms.acceptPrefix') }}
        <button type="button" :class="linkButtonClass" @click.stop.prevent="openTerms">
          {{ t('auth.terms.acceptLink') }}
        </button>
      </span>
    </label>

    <p v-if="error" class="mt-1 pl-6 text-xs font-medium leading-snug text-red-600" role="alert">
      {{ error }}
    </p>

    <BaseDialog v-model="dialogOpen" :title="t('auth.terms.title')" width="600">
      <p class="mb-5 text-sm font-medium text-gray-500 dark:text-zinc-400">
        {{ t('auth.terms.lastUpdated') }}
      </p>

      <ul
        class="list-disc space-y-4 pl-5 text-md leading-relaxed text-gray-700 marker:text-[#1b5875] dark:text-zinc-300"
      >
        <li v-for="key in bodyKeys" :key="key">
          {{ t(`auth.terms.body.${key}`) }}
        </li>
      </ul>

      <template #actions>
        <BaseButton variant="outlined" custom-class="text-gray-700" @click="dialogOpen = false">
          {{ t('common.close') }}
        </BaseButton>
        <BaseButton @click="acceptTerms">
          {{ t('auth.terms.acceptButton') }}
        </BaseButton>
      </template>
    </BaseDialog>
  </div>
</template>
