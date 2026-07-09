<script setup lang="ts">
import type { MenuEntry, MenuItem, SubmenuItem } from '~/types/ui-menu';

withDefaults(
  defineProps<{
    items: MenuEntry[];
    width?: number;
    active?: boolean;
    pinned?: boolean;
  }>(),
  { width: 220, active: false, pinned: false },
);

defineEmits<{
  select: [item: MenuItem | SubmenuItem];
}>();
</script>

<template>
  <BaseContextMenu
    :items="items"
    :width="width"
    :active="active"
    :pinned="pinned"
    @select="$emit('select', $event)"
  />
</template>
