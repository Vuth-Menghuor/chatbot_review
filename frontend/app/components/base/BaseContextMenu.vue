<template>
  <BaseMenu :items="items" :width="width" @select="$emit('select', $event)">
    <template #activator="{ props: menuProps, isActive }">
      <div class="relative flex h-5 w-5 items-center justify-center">
        <PinIcon v-if="pinned"
          class="absolute h-3.5 w-3.5 rotate-45 text-gray-500 transition-[opacity,transform] duration-150 dark:text-zinc-400"
          :class="isActive || active
            ? 'scale-50 opacity-0'
            : 'scale-100 opacity-100 group-hover:scale-50 group-hover:opacity-0'
            " />
        <div class="absolute flex items-center justify-center transition-[opacity,transform] duration-150" :class="isActive || active
          ? 'scale-100 opacity-100'
          : 'scale-50 opacity-0 group-hover:scale-100 group-hover:opacity-100'
          ">
          <BaseIconButton v-bind="menuProps" :icon="MoreHorizontalIcon" size="x-small"
            :tooltip="tooltip" custom-class="text-medium-emphasis hover:text-high-emphasis" />
        </div>
      </div>
    </template>
  </BaseMenu>
</template>

<script setup lang="ts">
import { MoreHorizontalIcon, PinIcon } from 'lucide-vue-next';
import type { MenuEntry, MenuItem, SubmenuItem } from '~/types/ui-menu';

withDefaults(
  defineProps<{
    items: MenuEntry[];
    width?: number;
    active?: boolean;
    pinned?: boolean;
    tooltip?: string;
    location?: string;
    offset?: number | string | unknown[];
  }>(),
  {
    width: 220,
    active: false,
    pinned: false,
    location: 'end',
    offset: 5,
  },
);

defineEmits<{
  select: [item: MenuItem | SubmenuItem];
}>();
</script>
