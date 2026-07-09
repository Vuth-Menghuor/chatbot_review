<template>
  <BaseButton
    v-if="appearance === 'card'"
    variant="text"
    justify="start"
    block
    :disabled="disabled"
    :custom-class="[cardClass, customClass].filter(Boolean).join(' ')"
    v-bind="$attrs"
    @click="onClick"
  >
    <BaseIconButton
      v-if="icon"
      decorative
      :icon="icon"
      size="small"
      custom-class="pointer-events-none text-medium-emphasis"
    />
    <span class="truncate text-left text-sm font-medium text-high-emphasis dark:text-zinc-100">
      <slot>
        <template v-if="labelKey">{{ $t(labelKey) }}</template>
        <template v-else>{{ label }}</template>
      </slot>
    </span>
  </BaseButton>

  <BaseButton
    v-else
    variant="text"
    :square="rail"
    :block="!rail"
    :spaced="!rail && (shortcut || $slots.append) ? 'both' : undefined"
    :justify="rail ? 'center' : 'start'"
    :tooltip="rail ? tooltipText : undefined"
    tooltip-location="right"
    :disabled="disabled"
    :custom-class="[buttonClass, customClass].filter(Boolean).join(' ')"
    v-bind="$attrs"
    @click="onClick"
  >
    <template v-if="rail">
      <BaseIconButton
        v-if="icon"
        decorative
        :icon="icon"
        size="small"
        icon-class="text-high-emphasis group-hover:text-gray-700 dark:group-hover:text-zinc-300"
        custom-class="pointer-events-none text-high-emphasis group-hover:text-gray-700 dark:group-hover:text-zinc-300"
      />
    </template>

    <template v-if="!rail" #prepend>
      <div class="flex min-w-0 items-center gap-3">
        <BaseIconButton
          v-if="icon"
          decorative
          :icon="icon"
          size="small"
          icon-class="text-high-emphasis group-hover:text-gray-700 dark:group-hover:text-zinc-300"
          custom-class="pointer-events-none text-high-emphasis group-hover:text-gray-700 dark:group-hover:text-zinc-300"
        />
        <span class="truncate text-base font-medium text-high-emphasis dark:text-zinc-100">
          <template v-if="labelKey">{{ $t(labelKey) }}</template>
          <template v-else>{{ label }}</template>
        </span>
      </div>
    </template>

    <template v-if="!rail && (shortcut || $slots.append)" #append>
      <slot name="append">
        <kbd
          v-if="shortcut"
          class="flex h-5 shrink-0 items-center rounded border border-gray-700 bg-gray-800 px-1.5 font-mono text-[11px] text-white dark:border-zinc-300 dark:bg-zinc-100 dark:text-black"
        >
          {{ shortcut }}
        </kbd>
      </slot>
    </template>
  </BaseButton>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue';

const cardClass =
  'min-h-13 gap-4 rounded-xl border border-opacity-25 bg-surface p-4 text-left normal-case tracking-normal shadow-none hover:bg-surface-variant';

const sidebarClass =
  'h-10 outline-none transition-[background-color,border-color,color] text-gray-500 dark:text-zinc-400 hover:!bg-gray-100 hover:!text-gray-700 dark:hover:!bg-zinc-800 dark:hover:!text-zinc-300 [&_.v-btn__overlay]:!opacity-0 [&_.v-btn__underlay]:!opacity-0 [&_.lucide]:text-high-emphasis hover:[&_.lucide]:text-gray-700 dark:hover:[&_.lucide]:text-zinc-300';

const sidebarBorderedClass =
  'rounded-lg border border-gray-200 dark:border-zinc-700 hover:border-gray-200 dark:hover:border-zinc-700';

export type BaseActionRowAppearance = 'sidebar' | 'card';

interface Props {
  appearance?: BaseActionRowAppearance;
  icon?: Component;
  label?: string;
  labelKey?: string;
  shortcut?: string;
  rail?: boolean;
  tooltip?: string;
  disabled?: boolean;
  customClass?: string;
}

const props = withDefaults(defineProps<Props>(), {
  appearance: 'sidebar',
  rail: false,
  disabled: false,
});

const emit = defineEmits<{
  click: [event: MouseEvent | KeyboardEvent];
}>();

defineOptions({ inheritAttrs: false });

const tooltipText = computed(() => props.tooltip ?? props.label ?? '');

const buttonClass = computed(() => {
  if (props.rail) {
    return `${sidebarClass} ml-1 w-10 min-w-0 border-0 px-0 shadow-none`;
  }
  return `${sidebarClass} ${sidebarBorderedClass} w-full min-w-0 px-3`;
});

function onClick(event: MouseEvent | KeyboardEvent) {
  if (props.disabled) return;
  emit('click', event);
}
</script>
