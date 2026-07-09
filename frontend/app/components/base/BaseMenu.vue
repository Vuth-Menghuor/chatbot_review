<script setup lang="ts">
import type {
  MenuEntry,
  MenuItem,
  MenuItemTone,
  SubmenuItem,
  TooltipLocation,
} from '~/types/ui-menu';

interface Props {
  items?: MenuEntry[];
  width?: string | number;
  fullWidth?: boolean;
  tone?: MenuItemTone;
  bgColor?: string;
  plain?: boolean;
  listClass?: string;
  transition?: string;
  offset?: number | string | number[];
  location?: TooltipLocation;
  openOnHover?: boolean;
  closeOnContentClick?: boolean;
}

withDefaults(defineProps<Props>(), {
  items: () => [],
  width: 210,
  fullWidth: false,
  tone: 'menu',
  transition: 'scale-transition',
  offset: 8,
  location: 'bottom start',
  openOnHover: false,
  plain: false,
  listClass: '',
  closeOnContentClick: true,
});

const open = defineModel<boolean>({ default: false });

const emit = defineEmits<{
  select: [item: MenuItem | SubmenuItem];
}>();

function onSelect(item: MenuItem | SubmenuItem) {
  open.value = false;
  emit('select', item);
}

defineOptions({ inheritAttrs: false });
</script>

<template>
  <v-menu
    v-model="open"
    v-bind="$attrs"
    :location="location"
    :transition="transition"
    :offset="offset"
    :open-on-hover="openOnHover"
    :close-on-content-click="closeOnContentClick"
    class="overflow-hidden rounded-xl"
  >
    <template #activator="{ props: activatorProps, isActive }">
      <slot name="activator" :props="activatorProps" :is-active="isActive" />
    </template>

    <BaseMenuList
      :items="items"
      :width="width"
      :full-width="fullWidth"
      :tone="tone"
      :bg-color="bgColor"
      :plain="plain"
      :list-class="listClass"
      @select="onSelect"
    >
      <template v-if="$slots.prepend" #prepend>
        <slot name="prepend" />
      </template>
      <template v-if="$slots.header" #header>
        <slot name="header" />
      </template>
      <slot />
    </BaseMenuList>
  </v-menu>
</template>
